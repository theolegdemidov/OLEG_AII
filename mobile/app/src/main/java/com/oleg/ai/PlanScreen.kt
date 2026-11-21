package com.oleg.ai

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale
import java.util.UUID
import kotlin.random.Random

private data class Picked(val uri: String, val name: String)

private fun displayName(context: Context, uri: Uri): String {
    var name = "video"
    context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
        if (c.moveToFirst()) {
            val n = c.getString(0)
            if (n != null) name = n
        }
    }
    return name
}

private val fmt = DateTimeFormatter.ofPattern("EEE d MMM, HH:mm", Locale("ru"))
private fun whenText(ms: Long): String = Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).format(fmt)

@Composable
fun PlanScreen() {
    val context = LocalContext.current
    var items by remember { mutableStateOf(PlanStore.load(context)) }
    var picked by remember { mutableStateOf<List<Picked>>(emptyList()) }
    var startOffset by remember { mutableIntStateOf(0) }
    var perDay by remember { mutableIntStateOf(1) }
    var slotsText by remember { mutableStateOf("12:00, 15:00, 18:30") }
    var jitterText by remember { mutableStateOf("20") }
    var captionsText by remember { mutableStateOf("") }
    var hashtags by remember { mutableStateOf("") }
    var shareFor by remember { mutableStateOf<PlanItem?>(null) }
    var editFor by remember { mutableStateOf<PlanItem?>(null) }
    var editText by remember { mutableStateOf("") }

    fun commit(list: List<PlanItem>) {
        items = list
        PlanStore.save(context, list)
    }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris: List<Uri> ->
        picked = uris.map { u ->
            try {
                context.contentResolver.takePersistableUriPermission(u, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            } catch (e: SecurityException) {
                // не все провайдеры дают постоянный доступ; тогда файл придётся выбрать заново
            }
            Picked(u.toString(), displayName(context, u))
        }
    }

    shareFor?.let { item ->
        AlertDialog(
            onDismissRequest = { shareFor = null },
            title = { Text("Куда публикуем?") },
            text = { Text("Подпись скопируется в буфер. В открывшемся приложении ты сам нажимаешь «Опубликовать».") },
            confirmButton = {
                Column {
                    TextButton(onClick = { shareFor = null; shareVideo(context, Uri.parse(item.uri), item.caption, "com.zhiliaoapp.musically") }) { Text("TikTok") }
                    TextButton(onClick = { shareFor = null; shareVideo(context, Uri.parse(item.uri), item.caption, "com.instagram.android") }) { Text("Instagram") }
                    TextButton(onClick = { shareFor = null; shareVideo(context, Uri.parse(item.uri), item.caption, "com.google.android.youtube") }) { Text("YouTube") }
                    TextButton(onClick = { shareFor = null; shareVideo(context, Uri.parse(item.uri), item.caption, null) }) { Text("Другое приложение…") }
                }
            },
            dismissButton = { TextButton(onClick = { shareFor = null }) { Text("Отмена") } }
        )
    }

    editFor?.let { item ->
        AlertDialog(
            onDismissRequest = { editFor = null },
            title = { Text("Подпись") },
            text = { OutlinedTextField(value = editText, onValueChange = { editText = it }, modifier = Modifier.fillMaxWidth()) },
            confirmButton = {
                TextButton(onClick = {
                    commit(items.map { if (it.id == item.id) it.copy(caption = editText) else it })
                    editFor = null
                }) { Text("Сохранить") }
            },
            dismissButton = { TextButton(onClick = { editFor = null }) { Text("Отмена") } }
        )
    }

    Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
        Text("План публикаций", fontWeight = FontWeight.Bold)
        Text(
            "Выбери несколько роликов. Приложение распределит их по дням и времени и напомнит. " +
                "В назначенное время нажимаешь уведомление и публикуешь в один тап.",
            style = MaterialTheme.typography.bodySmall
        )
        Spacer(Modifier.height(8.dp))
        Button(onClick = { picker.launch(arrayOf("video/*")) }, modifier = Modifier.fillMaxWidth()) {
            Text(if (picked.isEmpty()) "Выбрать ролики (можно много)" else "Выбрано: ${picked.size}. Выбрать заново")
        }
        picked.take(20).forEach { Text("• ${it.name}", style = MaterialTheme.typography.bodySmall) }

        Spacer(Modifier.height(10.dp))
        Text("Начать с", fontWeight = FontWeight.Bold)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf(0 to "Сегодня", 1 to "Завтра", 2 to "Через 2 дня").forEach { (off, label) ->
                if (startOffset == off) Button(onClick = { startOffset = off }) { Text(label) }
                else OutlinedButton(onClick = { startOffset = off }) { Text(label) }
            }
        }
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Роликов в день: $perDay", modifier = Modifier.padding(top = 10.dp))
            OutlinedButton(onClick = { if (perDay > 1) perDay-- }) { Text("-") }
            OutlinedButton(onClick = { if (perDay < 3) perDay++ }) { Text("+") }
        }
        OutlinedTextField(
            value = slotsText, onValueChange = { slotsText = it },
            label = { Text("Время слотов (чередуются по дням)") }, modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = jitterText, onValueChange = { jitterText = it.filter { c -> c.isDigit() }.take(3) },
            label = { Text("Случайный сдвиг, минут (±)") }, modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = captionsText, onValueChange = { captionsText = it },
            label = { Text("Подписи, по одной на строку (чередуются)") }, modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = hashtags, onValueChange = { hashtags = it },
            label = { Text("Общие хэштеги") }, modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(8.dp))
        Button(
            enabled = picked.isNotEmpty(),
            modifier = Modifier.fillMaxWidth(),
            onClick = {
                val slots = parseSlots(slotsText)
                if (slots.isEmpty()) {
                    Toast.makeText(context, "Укажи время, например 12:00, 15:00", Toast.LENGTH_LONG).show()
                } else {
                    val times = buildSchedule(
                        picked.size, startOffset, slots, perDay,
                        jitterText.toIntOrNull() ?: 0, ZonedDateTime.now(), Random.Default
                    )
                    val caps = captionsText.lines().map { it.trim() }.filter { it.isNotEmpty() }
                    val created = picked.zip(times).mapIndexed { i, (p, t) ->
                        val base = if (caps.isEmpty()) "" else caps[i % caps.size]
                        PlanItem(UUID.randomUUID().toString(), p.uri, p.name, "$base $hashtags".trim(), t, "planned")
                    }
                    created.forEach { Reminders.schedule(context, it) }
                    commit(items + created)
                    Toast.makeText(context, "В плане: ${created.size}", Toast.LENGTH_SHORT).show()
                    picked = emptyList()
                }
            }
        ) { Text("Составить расписание") }

        Spacer(Modifier.height(16.dp))
        Text("Очередь (${items.count { it.status == "planned" }})", fontWeight = FontWeight.Bold)
        val now = System.currentTimeMillis()
        items.sortedWith(compareBy({ it.status != "planned" }, { it.whenMillis })).forEach { item ->
            Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp).animateContentSize()) {
                Column(modifier = Modifier.padding(10.dp)) {
                    Text(item.name, fontWeight = FontWeight.Bold)
                    val state = when {
                        item.status == "done" -> "опубликовано"
                        item.whenMillis <= now -> "пора публиковать"
                        else -> "запланировано"
                    }
                    Text("${whenText(item.whenMillis)} · $state", style = MaterialTheme.typography.bodySmall)
                    if (item.caption.isNotBlank()) Text(item.caption, style = MaterialTheme.typography.bodySmall)
                    Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                        if (item.status == "planned") {
                            TextButton(onClick = { shareFor = item }) { Text("Опубликовать") }
                            TextButton(onClick = {
                                Reminders.cancel(context, item.id)
                                commit(items.map { if (it.id == item.id) it.copy(status = "done") else it })
                            }) { Text("Готово") }
                        }
                        TextButton(onClick = { editFor = item; editText = item.caption }) { Text("Подпись") }
                        TextButton(onClick = {
                            Reminders.cancel(context, item.id)
                            commit(items.filter { it.id != item.id })
                        }) { Text("Удалить") }
                    }
                }
            }
        }
        if (items.isEmpty()) Text("План пуст.", style = MaterialTheme.typography.bodySmall)
    }
}
