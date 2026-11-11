package com.marknadsradar.app

import android.annotation.SuppressLint
import android.content.ContentValues
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.view.Gravity
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.SecureRandom
import kotlin.concurrent.thread

/**
 * Startar Pythons webbserver (samma app som på datorn) på 127.0.0.1 och visar den i en WebView.
 * Servern kräver en slumpad nyckel som bara den här appen känner till, så andra appar på telefonen
 * kan inte läsa din journal och dina portföljer via localhost.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var web: WebView
    private lateinit var status: TextView
    private var chooserCallback: ValueCallback<Array<Uri>>? = null

    private val chooser = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        chooserCallback?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(r.resultCode, r.data))
        chooserCallback = null
    }

    companion object {
        const val PORT = 8765
        @Volatile private var key: String? = null
        @Volatile private var started = false
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = FrameLayout(this)
        root.setBackgroundColor(Color.parseColor("#0A0E14"))
        root.fitsSystemWindows = true
        web = WebView(this)
        web.setBackgroundColor(Color.parseColor("#0A0E14"))
        web.visibility = android.view.View.INVISIBLE
        status = TextView(this).apply {
            text = "Startar Marknadsradar…"
            setTextColor(Color.parseColor("#E6EDF3"))
            textSize = 16f
            gravity = Gravity.CENTER
            setPadding(48, 48, 48, 48)
        }
        root.addView(web, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        root.addView(status, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        setContentView(root)

        with(web.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            mediaPlaybackRequiresUserGesture = true
        }
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val u = request.url
                if (u.host == "127.0.0.1") return false
                try { startActivity(Intent(Intent.ACTION_VIEW, u)) } catch (_: Exception) { }
                return true
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(w: WebView, cb: ValueCallback<Array<Uri>>, p: WebChromeClient.FileChooserParams): Boolean {
                chooserCallback?.onReceiveValue(null)
                chooserCallback = cb
                return try { chooser.launch(p.createIntent()); true } catch (_: Exception) { chooserCallback = null; false }
            }
        }
        web.setDownloadListener { url, _, contentDisposition, mime, _ -> saveDownload(url, contentDisposition, mime) }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else moveTaskToBack(true)
            }
        })

        boot()
    }

    private fun boot() {
        thread(name = "boot") {
            try {
                if (key == null) {
                    val b = ByteArray(18); SecureRandom().nextBytes(b)
                    key = android.util.Base64.encodeToString(b, android.util.Base64.URL_SAFE or android.util.Base64.NO_WRAP or android.util.Base64.NO_PADDING)
                }
                if (!started) {
                    if (!Python.isStarted()) Python.start(AndroidPlatform(this))
                    val staticDir = copyAssets()
                    val dataDir = File(filesDir, "data").apply { mkdirs() }
                    Python.getInstance().getModule("android_entry").callAttr("start", dataDir.absolutePath, staticDir.absolutePath, PORT, key)
                    started = true
                }
                if (waitForServer()) {
                    runOnUiThread {
                        web.loadUrl("http://127.0.0.1:$PORT/?key=$key")
                        web.visibility = android.view.View.VISIBLE
                        status.visibility = android.view.View.GONE
                    }
                } else {
                    val log = try { Python.getInstance().getModule("android_entry").callAttr("last_log", File(filesDir, "data").absolutePath).toString() } catch (_: Exception) { "" }
                    show("Servern startade inte.\n\n$log")
                }
            } catch (e: Throwable) {
                show("Fel vid start:\n${e.message}")
            }
        }
    }

    private fun show(msg: String) = runOnUiThread { status.text = msg; status.textSize = 12f; status.gravity = Gravity.START }

    private fun waitForServer(): Boolean {
        val deadline = System.currentTimeMillis() + 120_000
        while (System.currentTimeMillis() < deadline) {
            try {
                val c = URL("http://127.0.0.1:$PORT/api/status").openConnection() as HttpURLConnection
                c.setRequestProperty("Cookie", "mr_key=$key")
                c.connectTimeout = 1000; c.readTimeout = 3000
                val ok = c.responseCode == 200
                c.disconnect()
                if (ok) return true
            } catch (_: Exception) { }
            Thread.sleep(400)
        }
        return false
    }

    /** Kopierar webbfilerna (assets/static) till en vanlig mapp som Python kan läsa. Görs en gång per appversion. */
    private fun copyAssets(): File {
        val lastModified = File(applicationInfo.sourceDir).lastModified()  // ändras vid varje ny APK
        val dest = File(filesDir, "static_$lastModified")
        if (File(dest, "index.html").exists()) return dest
        filesDir.listFiles()?.filter { it.name.startsWith("static_") }?.forEach { it.deleteRecursively() }
        fun copy(path: String, to: File) {
            val list = assets.list(path)
            if (list.isNullOrEmpty()) {
                to.parentFile?.mkdirs()
                assets.open(path).use { i -> to.outputStream().use { o -> i.copyTo(o) } }
            } else {
                to.mkdirs()
                list.forEach { copy("$path/$it", File(to, it)) }
            }
        }
        copy("static", dest)
        return dest
    }

    private fun saveDownload(url: String, disposition: String?, mime: String?) {
        thread {
            try {
                val c = URL(url).openConnection() as HttpURLConnection
                CookieManager.getInstance().getCookie(url)?.let { c.setRequestProperty("Cookie", it) }
                val name = Regex("filename\\*?=\"?([^\";]+)\"?").find(disposition ?: "")?.groupValues?.get(1)
                    ?: Uri.parse(url).lastPathSegment ?: "marknadsradar.txt"
                val bytes = c.inputStream.use { it.readBytes() }
                c.disconnect()
                if (Build.VERSION.SDK_INT >= 29) {
                    val v = ContentValues().apply {
                        put(MediaStore.Downloads.DISPLAY_NAME, name)
                        put(MediaStore.Downloads.MIME_TYPE, mime ?: "application/octet-stream")
                        put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                    }
                    val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v)!!
                    contentResolver.openOutputStream(uri)!!.use { it.write(bytes) }
                } else {
                    val dir = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)!!
                    File(dir, name).writeBytes(bytes)
                }
                runOnUiThread { Toast.makeText(this, "Sparad i Hämtade filer: $name", Toast.LENGTH_LONG).show() }
            } catch (e: Exception) {
                runOnUiThread { Toast.makeText(this, "Kunde inte spara filen: ${e.message}", Toast.LENGTH_LONG).show() }
            }
        }
    }

    override fun onDestroy() {
        chooserCallback?.onReceiveValue(null)
        super.onDestroy()
    }
}
