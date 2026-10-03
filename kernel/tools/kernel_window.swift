// kernel_window.swift — カーネルの窓（WKWebView）。/Applications/カーネル.app/Contents/MacOS/kernel-window の元。
// 作り方: swiftc -O -o kernel-window kernel_window.swift -framework Cocoa -framework WebKit
// 10/3: 前の窓は元の文が残っておらず、メニューが無かった。macOS は「編集」メニューが無いと
//   ⌘C・⌘V・⌘X・⌘A が WKWebView に届かず、コピー・貼り付けができなかった（本人）。メニューを付けて作り直した。
import Cocoa
import WebKit

final class Mado: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate {
    let url: URL
    var window: NSWindow!
    var web: WKWebView!

    init(url: URL) { self.url = url }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.mainMenu = menu()
        let config = WKWebViewConfiguration()
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.uiDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1180, height: 820),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "カーネル"
        window.contentView = web
        window.delegate = self
        window.center()
        window.setFrameAutosaveName("kernel-window")
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        web.load(URLRequest(url: url))
    }

    // ── メニュー（編集が無いと ⌘C・⌘V が効かない）──
    func menu() -> NSMenu {
        let main = NSMenu()
        func add(_ title: String, _ items: [(String, Selector?, String)]) {
            let top = NSMenuItem()
            let sub = NSMenu(title: title)
            for (name, action, key) in items {
                if name == "-" { sub.addItem(.separator()); continue }
                sub.addItem(NSMenuItem(title: name, action: action, keyEquivalent: key))
            }
            top.submenu = sub
            main.addItem(top)
        }
        add("カーネル", [("カーネルを隠す", #selector(NSApplication.hide(_:)), "h"), ("-", nil, ""),
                       ("カーネルを終了", #selector(NSApplication.terminate(_:)), "q")])
        add("編集", [("取り消す", Selector(("undo:")), "z"), ("やり直す", Selector(("redo:")), "Z"), ("-", nil, ""),
                    ("切り取り", #selector(NSText.cut(_:)), "x"), ("コピー", #selector(NSText.copy(_:)), "c"),
                    ("貼り付け", #selector(NSText.paste(_:)), "v"), ("すべてを選択", #selector(NSText.selectAll(_:)), "a")])
        add("表示", [("読み込み直す", #selector(reload), "r")])
        add("ウインドウ", [("しまう", #selector(NSWindow.performMiniaturize(_:)), "m"),
                         ("閉じる", #selector(NSWindow.performClose(_:)), "w")])
        return main
    }

    @objc func reload() { web.reload() }

    // ── 閉じたら終わる。Dock を押したら前に出す ──
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil)
        return true
    }

    // ── うちのサーバー以外へ行くリンクは、ふだんのブラウザで開く ──
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let target = action.request.url, action.navigationType == .linkActivated, target.host != url.host {
            NSWorkspace.shared.open(target)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let target = action.request.url { NSWorkspace.shared.open(target) }   // target="_blank"
        return nil
    }

    // ── つながらない時は、何が起きたかを窓に出す（黙って白い窓にしない）──
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        FileHandle.standardError.write("kernel-window: 読み込み失敗: \(error.localizedDescription)\n".data(using: .utf8)!)
        webView.loadHTMLString("""
            <meta charset="utf-8"><body style="font-family:-apple-system;padding:2em">
            <h2>うちうちのサーバーにつながりませんでした</h2>
            <p>記録: <code>~/Library/Logs/kernel-ai.log</code></p>
            <p>いったん閉じて、もう一度アイコンを押してみてください。</p></body>
            """, baseURL: nil)
    }

    // ── confirm()・alert() も出す（前の窓では黙って false になっていた）──
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.runModal()
        completionHandler()
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "やめる")
        completionHandler(alert.runModal() == .alertFirstButtonReturn)
    }
}

guard CommandLine.arguments.count >= 2, let url = URL(string: CommandLine.arguments[1]) else {
    FileHandle.standardError.write("使い方: kernel-window <URL>\n".data(using: .utf8)!)
    exit(2)
}
let app = NSApplication.shared
app.setActivationPolicy(.regular)
let mado = Mado(url: url)
app.delegate = mado
app.run()
