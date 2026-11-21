package com.oleg.ai

import android.Manifest
import android.annotation.SuppressLint
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.google.gson.Gson
import java.time.LocalTime
import java.time.ZonedDateTime
import kotlin.random.Random

/** Один ролик в плане. status: planned | done. uri: content:// файл, выбранный владельцем. */
data class PlanItem(
    val id: String,
    val uri: String,
    val name: String,
    val caption: String,
    val whenMillis: Long,
    val status: String
)

object PlanStore {
    private val gson = Gson()
    private const val PREFS = "oleg_ai_plan"
    private const val KEY = "plan_v1"

    fun load(context: Context): List<PlanItem> {
        val json = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, null)
            ?: return emptyList()
        return try {
            gson.fromJson(json, Array<PlanItem>::class.java)?.toList() ?: emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun save(context: Context, items: List<PlanItem>) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY, gson.toJson(items)).apply()
    }
}

/**
 * Раскладывает `count` роликов по дням и слотам. Слоты чередуются по кругу, поэтому в разные дни
 * время разное; jitter добавляет случайный сдвиг в минутах. Прошедшее время пропускается.
 */
fun buildSchedule(
    count: Int,
    startDayOffset: Int,
    slots: List<LocalTime>,
    perDay: Int,
    jitterMin: Int,
    now: ZonedDateTime,
    rnd: Random
): List<Long> {
    if (count <= 0 || slots.isEmpty()) return emptyList()
    val per = perDay.coerceIn(1, slots.size)
    val out = mutableListOf<Long>()
    var day = now.toLocalDate().plusDays(startDayOffset.toLong())
    var dayIndex = 0
    while (out.size < count && dayIndex < 400) {
        for (k in 0 until per) {
            if (out.size >= count) break
            val slot = slots[(dayIndex * per + k) % slots.size]
            val jitter = if (jitterMin > 0) rnd.nextInt(-jitterMin, jitterMin + 1) else 0
            val t = ZonedDateTime.of(day, slot, now.zone).plusMinutes(jitter.toLong())
            if (t.isAfter(now.plusMinutes(1))) out.add(t.toInstant().toEpochMilli())
        }
        day = day.plusDays(1)
        dayIndex++
    }
    return out.sorted()
}

/** "12:00, 15:30 18:00" -> список времени. Мусор отбрасывается. */
fun parseSlots(text: String): List<LocalTime> {
    val found = Regex("(\\d{1,2}):(\\d{2})").findAll(text).mapNotNull {
        val h = it.groupValues[1].toInt()
        val m = it.groupValues[2].toInt()
        if (h in 0..23 && m in 0..59) LocalTime.of(h, m) else null
    }.distinct().toList()
    return found.sorted()
}

object Reminders {
    const val ACTION_REMIND = "com.oleg.ai.REMIND"
    const val EXTRA_ID = "item_id"
    private const val CHANNEL = "publish_reminders"

    private fun pending(context: Context, id: String): PendingIntent {
        val i = Intent(context, ReminderReceiver::class.java).setAction(ACTION_REMIND).putExtra(EXTRA_ID, id)
        return PendingIntent.getBroadcast(
            context, id.hashCode(), i, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
    }

    /** Неточный будильник: не требует спецразрешения, может сработать с задержкой в Doze. */
    fun schedule(context: Context, item: PlanItem) {
        if (item.status != "planned" || item.whenMillis <= System.currentTimeMillis()) return
        val am = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, item.whenMillis, pending(context, item.id))
    }

    fun cancel(context: Context, id: String) {
        val am = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        am.cancel(pending(context, id))
    }

    fun scheduleAll(context: Context) {
        PlanStore.load(context).forEach { schedule(context, it) }
    }

    @SuppressLint("MissingPermission")
    fun notifyItem(context: Context, id: String) {
        val item = PlanStore.load(context).firstOrNull { it.id == id && it.status == "planned" } ?: return
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) return
        if (Build.VERSION.SDK_INT >= 26) {
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "Напоминания о публикации", NotificationManager.IMPORTANCE_HIGH)
            )
        }
        val open = PendingIntent.getActivity(
            context, id.hashCode(),
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                .putExtra(EXTRA_ID, id),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val n = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Пора публиковать")
            .setContentText(item.name)
            .setContentIntent(open)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        NotificationManagerCompat.from(context).notify(id.hashCode(), n)
    }
}

class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED -> Reminders.scheduleAll(context)
            Reminders.ACTION_REMIND -> {
                val id = intent.getStringExtra(Reminders.EXTRA_ID)
                if (id != null) Reminders.notifyItem(context, id)
            }
        }
    }
}
