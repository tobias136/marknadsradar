package com.marknadsradar.app

import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.CookieHandler
import java.net.CookieManager
import java.net.CookiePolicy
import java.net.HttpURLConnection
import java.net.URL

/**
 * HTTP-anrop åt Pythons Yahoo-klient (app/yahoo_http.py, AndroidTransport).
 * Telefonens egen nätverksstack används, med cookies i en gemensam CookieManager.
 */
object YahooHttp {
    private const val UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    private val cookies = CookieManager(null, CookiePolicy.ACCEPT_ALL)

    init {
        CookieHandler.setDefault(cookies)
    }

    @JvmStatic
    fun clearCookies() {
        cookies.cookieStore.removeAll()
    }

    /** Returnerar [status, slutlig url, svarstext]. Följer upp till 8 omdirigeringar och behåller cookies. */
    @JvmStatic
    fun request(method: String, url: String, body: String, headersJson: String): Array<String> {
        var m = method
        var u = url
        var payload: String? = if (body.isNotEmpty()) body else null
        val extra = JSONObject(if (headersJson.isEmpty()) "{}" else headersJson)
        repeat(9) {
            val c = URL(u).openConnection() as HttpURLConnection
            try {
                c.instanceFollowRedirects = false
                c.connectTimeout = 15000
                c.readTimeout = 30000
                c.requestMethod = m
                c.setRequestProperty("User-Agent", UA)
                c.setRequestProperty("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
                c.setRequestProperty("Accept-Language", "en-US,en;q=0.5")
                val keys = extra.keys()
                while (keys.hasNext()) {
                    val k = keys.next()
                    c.setRequestProperty(k, extra.getString(k))
                }
                if (payload != null && (m == "POST" || m == "PUT")) {
                    c.doOutput = true
                    if (c.getRequestProperty("Content-Type") == null) {
                        c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
                    }
                    c.outputStream.use { it.write(payload!!.toByteArray(Charsets.UTF_8)) }
                }
                val status = c.responseCode
                if (status in listOf(301, 302, 303, 307, 308)) {
                    val loc = c.getHeaderField("Location")
                    if (loc != null) {
                        u = URL(URL(u), loc).toString()
                        if (status == 301 || status == 302 || status == 303) {
                            m = "GET"
                            payload = null
                        }
                        return@repeat
                    }
                }
                val stream = if (status >= 400) c.errorStream else c.inputStream
                val out = ByteArrayOutputStream()
                stream?.use { it.copyTo(out) }
                return arrayOf(status.toString(), u, out.toString("UTF-8"))
            } finally {
                c.disconnect()
            }
        }
        return arrayOf("310", u, "För många omdirigeringar")
    }
}
