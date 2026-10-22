package com.innoverce26.app

import android.app.Activity
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.TextView
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val startupExecutor = Executors.newSingleThreadExecutor()
    private var webView: WebView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.BLACK
        window.navigationBarColor = Color.BLACK

        val browser = WebView(this).apply {
            setBackgroundColor(Color.BLACK)
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(
                    view: WebView,
                    request: WebResourceRequest
                ): Boolean {
                    val uri = request.url
                    return !uri.isLocalAppUrl()
                }
            }
        }
        webView = browser
        CookieManager.getInstance().setAcceptCookie(true)
        setContentView(
            browser,
            ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        )

        startupExecutor.execute {
            try {
                val siteDirectory = File(filesDir, "site")
                copyBundledSite(siteDirectory)
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(applicationContext))
                }
                val python = Python.getInstance()
                val server = python.getModule("android_server")
                val port = server.callAttr(
                    "start_server",
                    siteDirectory.absolutePath,
                    filesDir.absolutePath,
                    LOCAL_SERVER_PORT
                ).toInt()
                runOnUiThread {
                    browser.loadUrl("http://127.0.0.1:$port/auth.html?mode=login")
                }
            } catch (error: Exception) {
                runOnUiThread { showStartupError(error) }
            }
        }
    }

    private fun copyBundledSite(destination: File) {
        val assets = assets
        val pendingDirectories = ArrayDeque<Pair<String, File>>()
        pendingDirectories.add("" to destination)

        while (pendingDirectories.isNotEmpty()) {
            val (assetDirectory, outputDirectory) = pendingDirectories.removeFirst()
            if (!outputDirectory.exists() && !outputDirectory.mkdirs()) {
                error("Could not create app site directory.")
            }
            val entries = assets.list(assetDirectory)
                ?: error("Could not read bundled site assets.")

            for (entry in entries) {
                val assetPath = if (assetDirectory.isEmpty()) entry else "$assetDirectory/$entry"
                val output = File(outputDirectory, entry)
                val children = assets.list(assetPath)
                if (children != null && children.isNotEmpty()) {
                    pendingDirectories.add(assetPath to output)
                } else {
                    assets.open(assetPath).use { input ->
                        output.outputStream().use { outputStream -> input.copyTo(outputStream) }
                    }
                }
            }
        }
    }

    private fun showStartupError(error: Exception) {
        val message = TextView(this).apply {
            text = "Innoverce 26 could not start its local service.\n\n${error.message ?: error.javaClass.simpleName}"
            setTextColor(Color.WHITE)
            textSize = 16f
            gravity = Gravity.CENTER
            setPadding(32, 32, 32, 32)
            setBackgroundColor(Color.BLACK)
        }
        setContentView(message)
    }

    override fun onBackPressed() {
        val browser = webView
        if (browser?.canGoBack() == true) {
            browser.goBack()
        } else {
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        startupExecutor.shutdown()
        webView?.destroy()
        webView = null
        super.onDestroy()
    }

    private fun Uri.isLocalAppUrl(): Boolean =
        scheme == "http" && host == "127.0.0.1" && port == LOCAL_SERVER_PORT

    companion object {
        private const val LOCAL_SERVER_PORT = 8765
    }
}
