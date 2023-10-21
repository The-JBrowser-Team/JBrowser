import sys
import os
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtWebEngineWidgets import *

class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0faff;
            }
            QTabWidget::pane {
                border: 1px solid #aad8e6;
                background-color: #f0faff;
            }
            QTabWidget::tab-bar {
                alignment: center;
            }
            QTabBar::tab {
                background-color: #d5ebf7;
                border: 1px solid #aad8e6;
                padding: 6px;
                min-width: 100px;
                min-height: 30px;
            }
            QTabBar::tab:selected {
                background-color: #f0faff;
            }
            QToolBar {
                background-color: #d5ebf7;
                border: 1px solid #aad8e6;
            }
            QLineEdit {
                background-color: #f0faff;
                border: 1px solid #aad8e6;
                padding: 2px;
            }
        """)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBarDoubleClicked.connect(self.tab_open_double_click)
        self.tabs.currentChanged.connect(self.current_tab_changed)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_current_tab)
        self.setCentralWidget(self.tabs)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        navtb = QToolBar("Navigation")
        self.addToolBar(navtb)

        actions = [
            ("◀", "Back to previous page", lambda: self.tabs.currentWidget().back()),
            ("▶", "Forward to next page", lambda: self.tabs.currentWidget().forward()),
            ("Reload", "Reload page", lambda: self.tabs.currentWidget().reload()),
            ("Home", "Go home", self.navigate_home),
            ("Stop", "Stop loading current page", lambda: self.tabs.currentWidget().stop())
        ]

        for icon, tooltip, action in actions:
            button = QAction(icon, self)
            button.setStatusTip(tooltip)
            button.triggered.connect(action)
            navtb.addAction(button)

        navtb.addSeparator()

        self.urlbar = QLineEdit()
        self.urlbar.returnPressed.connect(self.navigate_to_url)
        navtb.addWidget(self.urlbar)

        self.add_new_tab('Homepage')

        self.show()
        self.setWindowTitle("Home")

    def add_new_tab(self, label="Blank"):
        script_dir = os.path.dirname(os.path.abspath(__file__))  # Get the directory of the Python script
        html_file_path = os.path.join(script_dir, "JBrowserHTMLEncoding.html")

        if os.path.exists(html_file_path):
            qurl = QUrl.fromLocalFile(html_file_path)
            browser = QWebEngineView()
            browser.setUrl(qurl)
            
            # Set the zoom factor to 1.5 (150%)
            browser.setZoomFactor(1.5)
            
            browser.urlChanged.connect(lambda qurl, browser=browser: self.update_urlbar(qurl))
            browser.loadFinished.connect(lambda _, browser=browser: self.update_tab_title(browser))
            self.tabs.addTab(browser, label)
            self.tabs.setCurrentWidget(browser)

    def update_tab_title(self, browser):
        title = browser.page().title()
        self.tabs.setTabText(self.tabs.indexOf(browser), title)

    def tab_open_double_click(self):
        self.add_new_tab()

    def current_tab_changed(self):
        qurl = self.tabs.currentWidget().url()
        self.update_urlbar(qurl)
        self.update_title(self.tabs.currentWidget())

    def close_current_tab(self, i):
        if self.tabs.count() > 1:
            self.tabs.removeTab(i)

    def navigate_home(self):
        self.tabs.currentWidget().setUrl(QUrl.fromLocalFile("JBrowserHTMLEncoding.html"))  # Assuming it's in the script's directory

    def navigate_to_url(self):
        q = QUrl(self.urlbar.text())
        if q.scheme() == "":
            q.setScheme("http")
        self.tabs.currentWidget().setUrl(q)

    def update_urlbar(self, q):
        if q == self.tabs.currentWidget().url():
            self.urlbar.setText(q.toString())
            self.urlbar.setCursorPosition(0)

    def update_title(self, browser):
        title = browser.page().title()
        self.setWindowTitle(f"{title} - JBrowser")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("JBrowser")
    window = MainWindow()
    sys.exit(app.exec_())
