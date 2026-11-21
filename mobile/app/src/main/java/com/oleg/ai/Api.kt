package com.oleg.ai

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import okhttp3.MediaType
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.RequestBody
import okio.BufferedSink
import okio.source
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Query
import java.util.concurrent.TimeUnit

// Все поля nullable: Gson кладёт null для отсутствующих полей, и non-null типы Kotlin дали бы падение.
data class CardsResponse(val items: List<CardDto>?)
data class CardDto(
    val video: VideoDto?,
    val analysis: AnalysisDto?,
    val drafts: List<DraftDto>?,
    val growth: GrowthDto?
)
data class VideoDto(
    val id: String?, val title: String?, val channel: String?,
    val views: Long?, val subs: Long?, val ratio: Double?,
    val views_per_day: Long?, val shorts_url: String?
)
data class GrowthDto(val views_delta: Long?, val hours: Double?)
data class AnalysisDto(
    val facts: List<String>?, val hypotheses: List<String>?, val ab_hooks: List<String>?,
    val ideas: List<IdeaDto>?, val missing_data: List<String>?
)
data class IdeaDto(val hook: String?, val thesis: String?, val visual: String?, val cta: String?)
data class DraftDto(val id: Int, val text: String?, val status: String?, val final_text: String?)

data class FeedbackRequest(val draft_id: Int, val status: String, val final_text: String?)
data class StyleRequest(val phrase: String)

data class OkResponse(val ok: Boolean?, val added: Boolean?, val imported: Int?)
data class HealthDto(val status: String?)
data class ResearchStatusDto(
    val running: Boolean?, val error: String?, val result: ResearchResultDto?
)
data class ResearchResultDto(val found: Int?, val analyzed: Int?, val failed: Int?, val error: String?)
data class RunResponse(val started: Boolean?, val status: ResearchStatusDto?)
data class OwnReportDto(val text: String?)

data class VideoAuditResponse(
    val ok: Boolean?, val hook_score: Double?, val first_2_sec_verdict: String?,
    val transcript_summary: String?, val weak_spots: List<String>?,
    val improved_hooks: List<String>?, val best_title_and_tags: String?, val error: String?
)

interface OlegApi {
    @GET("health") suspend fun health(): HealthDto
    @GET("cards") suspend fun cards(@Query("limit") limit: Int): CardsResponse
    @POST("research/run") suspend fun runResearch(): RunResponse
    @GET("research/status") suspend fun researchStatus(): ResearchStatusDto
    @POST("feedback") suspend fun feedback(@Body body: FeedbackRequest): OkResponse
    @POST("style") suspend fun addStyle(@Body body: StyleRequest): OkResponse
    @GET("own/report") suspend fun ownReport(): OwnReportDto

    @Multipart
    @POST("video/analyze")
    suspend fun analyzeVideo(@Part file: MultipartBody.Part): VideoAuditResponse

    companion object {
        fun create(baseUrl: String, token: String): OlegApi {
            val url = baseUrl.trim().let { if (it.endsWith("/")) it else "$it/" }
            val client = OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(10, TimeUnit.MINUTES) // разбор видео может быть долгим
                .writeTimeout(10, TimeUnit.MINUTES)
                .addInterceptor { chain ->
                    chain.proceed(chain.request().newBuilder().header("X-API-Key", token.trim()).build())
                }
                .build()
            return Retrofit.Builder().baseUrl(url).client(client)
                .addConverterFactory(GsonConverterFactory.create())
                .build().create(OlegApi::class.java)
        }
    }
}

/** Потоковая отправка файла: видео не загружается в память целиком (на A52 это вызвало бы OutOfMemory). */
class UriRequestBody(
    private val resolver: ContentResolver,
    private val uri: Uri,
    private val type: MediaType?
) : RequestBody() {
    override fun contentType(): MediaType? = type
    override fun contentLength(): Long =
        resolver.openAssetFileDescriptor(uri, "r")?.use { it.length } ?: -1L
    override fun writeTo(sink: BufferedSink) {
        resolver.openInputStream(uri)?.use { sink.writeAll(it.source()) }
    }
}

fun videoPart(resolver: ContentResolver, uri: Uri): MultipartBody.Part {
    var name = "upload.mp4"
    resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
        if (c.moveToFirst()) {
            val n = c.getString(0)
            if (n != null && n.contains('.')) name = n
        }
    }
    val mime = (resolver.getType(uri) ?: "video/mp4").toMediaTypeOrNull()
    return MultipartBody.Part.createFormData("file", name, UriRequestBody(resolver, uri, mime))
}
