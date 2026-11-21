package com.oleg.ai

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.Crossfade
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 33) {
            registerForActivityResult(ActivityResultContracts.RequestPermission()) { }
                .launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        Reminders.scheduleAll(this) // восстановить будильники после обновления приложения
        val startTab = if (intent?.hasExtra(Reminders.EXTRA_ID) == true) 1 else 0
        setContent {
            OlegTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) { AppRoot(startTab) }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppRoot(startTab: Int) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val prefs = remember { context.getSharedPreferences("oleg_ai_prefs", Context.MODE_PRIVATE) }

    var serverUrl by remember { mutableStateOf(prefs.getString("server_url", "http://192.168.1.100:8000") ?: "") }
    var token by remember { mutableStateOf(prefs.getString("api_token", "") ?: "") }
    var tab by remember { mutableIntStateOf(startTab) }
    var cards by remember { mutableStateOf<List<CardDto>>(emptyList()) }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    var picked by remember { mutableStateOf<Uri?>(null) }
    var audit by remember { mutableStateOf<VideoAuditResponse?>(null) }
    var caption by remember { mutableStateOf("") }
    var ownReport by remember { mutableStateOf("") }
    var stylePhrase by remember { mutableStateOf("") }
    var editing by remember { mutableStateOf<DraftDto?>(null) }
    var editText by remember { mutableStateOf("") }

    fun api(): OlegApi = OlegApi.create(serverUrl, token)
    fun toast(msg: String) = Toast.makeText(context, msg, Toast.LENGTH_LONG).show()

    fun launchSafely(block: suspend () -> Unit) {
        scope.launch {
            busy = true
            try {
                block()
            } catch (e: Exception) {
                toast("Ошибка: ${e.message ?: e.javaClass.simpleName}")
            } finally {
                busy = false
            }
        }
    }

    suspend fun loadCards() {
        cards = api().cards(30).items ?: emptyList()
    }

    fun sendFeedback(draftId: Int, st: String, text: String?) = launchSafely {
        api().feedback(FeedbackRequest(draftId, st, text))
        loadCards()
        toast(if (st == "rejected") "Учту: так не пишу" else "Сохранено в твой стиль")
    }

    val videoPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri != null) {
            picked = uri
            audit = null
        }
    }

    if (editing != null) {
        AlertDialog(
            onDismissRequest = { editing = null },
            title = { Text("Твоя версия комментария") },
            text = {
                OutlinedTextField(value = editText, onValueChange = { editText = it }, modifier = Modifier.fillMaxWidth())
            },
            confirmButton = {
                TextButton(onClick = {
                    val d = editing
                    editing = null
                    if (d != null && editText.isNotBlank()) sendFeedback(d.id, "edited", editText.trim())
                }) { Text("Сохранить") }
            },
            dismissButton = { TextButton(onClick = { editing = null }) { Text("Отмена") } }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("OLEG AI") },
                actions = {
                    TextButton(enabled = !busy, onClick = {
                        launchSafely {
                            val api = api()
                            val started = api.runResearch()
                            status = if (started.started == true) "Поиск запущен…" else "Поиск уже идёт…"
                            var tries = 0
                            while (tries < 200) {
                                delay(3000)
                                val s = api.researchStatus()
                                if (s.running != true) {
                                    status = s.error?.let { "Ошибка поиска: $it" }
                                        ?: "Готово: разобрано ${s.result?.analyzed ?: 0} из ${s.result?.found ?: 0}" +
                                        (if ((s.result?.failed ?: 0) > 0) ", ошибок LLM: ${s.result?.failed}" else "")
                                    loadCards()
                                    break
                                }
                                tries++
                            }
                        }
                    }) { Text("Найти тренды") }
                }
            )
        },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(selected = tab == 0, onClick = { tab = 0 }, label = { Text("Тренды") }, icon = {})
                NavigationBarItem(selected = tab == 1, onClick = { tab = 1 }, label = { Text("План") }, icon = {})
                NavigationBarItem(selected = tab == 2, onClick = { tab = 2 }, label = { Text("Разбор") }, icon = {})
                NavigationBarItem(selected = tab == 3, onClick = { tab = 3 }, label = { Text("Настройки") }, icon = {})
            }
        }
    ) { padding ->
        Column(modifier = Modifier.padding(padding).padding(14.dp).fillMaxSize()) {
            if (busy) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
            }
            if (status.isNotBlank()) {
                Text(status, style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(6.dp))
            }
            Crossfade(targetState = tab, animationSpec = tween(220), label = "tab") { current ->
            when (current) {
                0 -> {
                    Button(enabled = !busy, onClick = { launchSafely { loadCards() } }, modifier = Modifier.fillMaxWidth()) {
                        Text("Обновить ленту с ноутбука")
                    }
                    Spacer(Modifier.height(10.dp))
                    if (cards.isEmpty()) Text("Пока пусто. Нажми «Найти тренды» и подожди.")
                    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        items(cards) { card ->
                            TrendCard(
                                card = card,
                                onCopyAndOpen = { text, url -> copyAndOpenVideo(context, text, url) },
                                onAccept = { sendFeedback(it.id, "accepted", null) },
                                onEdit = { editing = it; editText = it.final_text ?: it.text ?: "" },
                                onReject = { sendFeedback(it.id, "rejected", null) }
                            )
                        }
                    }
                }

                1 -> PlanScreen()

                2 -> Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                    Text("Разбор и публикация моего видео", fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = { videoPicker.launch("video/*") }, modifier = Modifier.fillMaxWidth()) {
                        Text(if (picked == null) "Выбрать видео из галереи" else "Видео выбрано. Выбрать другое")
                    }
                    Spacer(Modifier.height(8.dp))
                    Button(
                        enabled = picked != null && !busy,
                        onClick = {
                            launchSafely {
                                val result = api().analyzeVideo(videoPart(context.contentResolver, picked!!))
                                audit = result
                                val suggested = result.best_title_and_tags
                                if (!suggested.isNullOrBlank() && caption.isBlank()) caption = suggested
                            }
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) { Text("Разобрать хук и слабые места (Gemini)") }
                    Spacer(Modifier.height(10.dp))
                    audit?.let { a ->
                        Card(modifier = Modifier.fillMaxWidth()) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                if (a.ok == true) {
                                    Text("Оценка хука: ${a.hook_score ?: 0.0}/10", fontWeight = FontWeight.Bold)
                                    Text("Первые 2 сек: ${a.first_2_sec_verdict ?: ""}")
                                    Text("Суть: ${a.transcript_summary ?: ""}")
                                    a.weak_spots?.takeIf { it.isNotEmpty() }?.let {
                                        Text("Слабые места:\n" + it.joinToString("\n") { s -> "- $s" })
                                    }
                                    a.improved_hooks?.takeIf { it.isNotEmpty() }?.let {
                                        Text("Хуки для A/B:\n" + it.joinToString("\n") { s -> "- $s" })
                                    }
                                } else {
                                    Text("Не получилось: ${a.error ?: "неизвестная ошибка"}")
                                }
                            }
                        }
                        Spacer(Modifier.height(10.dp))
                    }
                    OutlinedTextField(
                        value = caption, onValueChange = { caption = it },
                        label = { Text("Подпись и хэштеги") }, modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(Modifier.height(8.dp))
                    Text("Публикация вручную: подпись копируется в буфер, видео открывается в нужном приложении, нажимаешь «Опубликовать» сам.",
                        style = MaterialTheme.typography.bodySmall)
                    Spacer(Modifier.height(6.dp))
                    val uri = picked
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(enabled = uri != null, onClick = { shareVideo(context, uri!!, caption, "com.zhiliaoapp.musically") }) { Text("TikTok") }
                        OutlinedButton(enabled = uri != null, onClick = { shareVideo(context, uri!!, caption, "com.instagram.android") }) { Text("Instagram") }
                        OutlinedButton(enabled = uri != null, onClick = { shareVideo(context, uri!!, caption, "com.google.android.youtube") }) { Text("YouTube") }
                    }
                    Spacer(Modifier.height(4.dp))
                    OutlinedButton(enabled = uri != null, onClick = { shareVideo(context, uri!!, caption, null) }) { Text("Другое приложение…") }
                }

                else -> Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                    Text("Адрес ноутбука в домашней Wi-Fi сети", fontWeight = FontWeight.Bold)
                    OutlinedTextField(
                        value = serverUrl,
                        onValueChange = { serverUrl = it; prefs.edit().putString("server_url", it).apply() },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(Modifier.height(8.dp))
                    Text("API_TOKEN из файла .env на ноутбуке", fontWeight = FontWeight.Bold)
                    OutlinedTextField(
                        value = token,
                        onValueChange = { token = it; prefs.edit().putString("api_token", it).apply() },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(Modifier.height(8.dp))
                    Button(enabled = !busy, onClick = {
                        launchSafely {
                            api().health()
                            api().cards(1) // проверка токена: /health открыт, /cards нет
                            toast("Связь с ноутбуком есть, токен принят")
                        }
                    }) { Text("Проверить связь") }
                    Spacer(Modifier.height(16.dp))
                    Text("Добавить мою фразу в профиль стиля", fontWeight = FontWeight.Bold)
                    OutlinedTextField(value = stylePhrase, onValueChange = { stylePhrase = it }, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(8.dp))
                    Button(enabled = !busy && stylePhrase.isNotBlank(), onClick = {
                        launchSafely {
                            val r = api().addStyle(StyleRequest(stylePhrase))
                            toast(if (r.added == true) "Добавлено" else "Такая фраза уже есть")
                            stylePhrase = ""
                        }
                    }) { Text("Добавить") }
                    Spacer(Modifier.height(16.dp))
                    Button(enabled = !busy, onClick = { launchSafely { ownReport = api().ownReport().text ?: "" } }) {
                        Text("Разбор моих роликов (по CSV)")
                    }
                    if (ownReport.isNotBlank()) {
                        Spacer(Modifier.height(8.dp))
                        Text(ownReport, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            }
        }
    }
}

@Composable
fun TrendCard(
    card: CardDto,
    onCopyAndOpen: (String, String) -> Unit,
    onAccept: (DraftDto) -> Unit,
    onEdit: (DraftDto) -> Unit,
    onReject: (DraftDto) -> Unit
) {
    val v = card.video
    Card(modifier = Modifier.fillMaxWidth().animateContentSize()) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(v?.title ?: "(без названия)", fontWeight = FontWeight.Bold)
            Text(
                "${v?.channel ?: ""} · ${v?.views ?: 0} просм. · x${v?.ratio ?: 0.0} · ~${v?.views_per_day ?: 0}/день",
                style = MaterialTheme.typography.bodySmall
            )
            card.growth?.let {
                Text("Рост с прошлого замера: +${it.views_delta ?: 0} за ${it.hours ?: 0} ч.", style = MaterialTheme.typography.bodySmall)
            }
            Spacer(Modifier.height(8.dp))
            card.analysis?.ab_hooks?.takeIf { it.isNotEmpty() }?.let {
                Text("A/B-хуки для твоей анимации:\n" + it.joinToString("\n") { h -> "• $h" })
                Spacer(Modifier.height(6.dp))
            }
            card.analysis?.hypotheses?.takeIf { it.isNotEmpty() }?.let {
                Text("Гипотезы (не доказано):\n" + it.joinToString("\n") { h -> "• $h" }, style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(6.dp))
            }
            (card.drafts ?: emptyList()).forEach { d ->
                OutlinedCard(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                    Column(modifier = Modifier.padding(8.dp)) {
                        Text(d.final_text ?: d.text ?: "")
                        Text("Статус: ${d.status ?: ""}", style = MaterialTheme.typography.bodySmall)
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            TextButton(onClick = { onCopyAndOpen(d.final_text ?: d.text ?: "", v?.shorts_url ?: "") }) { Text("Копировать и открыть") }
                            TextButton(onClick = { onAccept(d) }) { Text("Принять") }
                            TextButton(onClick = { onEdit(d) }) { Text("Править") }
                            TextButton(onClick = { onReject(d) }) { Text("Нет") }
                        }
                    }
                }
            }
        }
    }
}

private fun copyToClipboard(context: Context, text: String) {
    val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    cm.setPrimaryClip(ClipData.newPlainText("OLEG AI", text))
}

/** Комментарий копируется, ролик открывается в приложении YouTube. Вставляешь и отправляешь сам. */
private fun copyAndOpenVideo(context: Context, text: String, url: String) {
    copyToClipboard(context, text)
    Toast.makeText(context, "Скопировано. Вставь в комментарий.", Toast.LENGTH_SHORT).show()
    if (url.isNotBlank()) {
        try {
            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(context, "Нечем открыть ссылку", Toast.LENGTH_SHORT).show()
        }
    }
}

/** Системное меню «Поделиться» для СВОЕГО видео. Финальное «Опубликовать» нажимает владелец. */
fun shareVideo(context: Context, uri: Uri, caption: String, pkg: String?) {
    copyToClipboard(context, caption)
    val send = Intent(Intent.ACTION_SEND).apply {
        type = "video/*"
        putExtra(Intent.EXTRA_STREAM, uri)
        putExtra(Intent.EXTRA_TEXT, caption)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        if (pkg != null) setPackage(pkg)
    }
    try {
        context.startActivity(if (pkg == null) Intent.createChooser(send, "Опубликовать") else send)
        Toast.makeText(context, "Подпись скопирована в буфер", Toast.LENGTH_SHORT).show()
    } catch (e: ActivityNotFoundException) {
        Toast.makeText(context, "Приложение не установлено", Toast.LENGTH_SHORT).show()
    }
}
