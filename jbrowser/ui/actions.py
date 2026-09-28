"""Registers every browser command with its shortcuts, palette keywords and live state."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QApplication

from jbrowser.core.settings import SLEEP_PRESETS
from jbrowser.services.network import DEV_PORTS, DNS_MODES

if TYPE_CHECKING:
    from jbrowser.context import AppContext
    from jbrowser.ui.controller import BrowserController


def register_commands(ctx: "AppContext", ui: "BrowserController") -> None:
    c = ctx.commands
    s = ctx.settings

    def on_off(key: str):
        return lambda: "On" if s.get(key) else "Off"

    # ----------------------------------------------------------------- cards
    CARDS = "Cards"
    c.add("card.new", "New card", CARDS, lambda: ui.open_lazy_toolbar("new"), shortcuts=["Ctrl+T"], icon="add",
          keywords="tab open new page")
    c.add("palette.open", "Open Lazy Toolbar", CARDS, lambda: ui.open_lazy_toolbar(
        "current" if ctx.state.active_tab else "new"), shortcuts=["Ctrl+K"], icon="search",
          keywords="command palette omnibox search", palette=False)
    c.add("card.edit_url", "Edit address", CARDS, lambda: ui.open_lazy_toolbar("edit"),
          shortcuts=["Ctrl+L", "F6", "Alt+D"], icon="edit", keywords="url location omnibox")
    c.add("card.close", "Close card", CARDS, lambda: ui.close_selected(), shortcuts=["Ctrl+W", "Ctrl+F4"],
          icon="close", keywords="tab")
    c.add("card.reopen", "Reopen closed card", CARDS, ui.reopen_closed, shortcuts=["Ctrl+Shift+T"], icon="history",
          keywords="undo close restore tab archive")
    c.add("archive.show", "Archive (cards closed in the last 48 hours)", CARDS, lambda: ui.show_archive(),
          shortcuts=["Ctrl+Shift+Y"], icon="archive", keywords="closed recently reopen history")
    c.add("card.pin", "Pin / unpin card", CARDS, lambda: ui.toggle_pin(), icon="pin",
          keywords="pinned keep sticky tab")
    c.add("card.favourite", "Add card to favourites / remove", CARDS, lambda: ui.toggle_favourite(), icon="star",
          keywords="favorite favourite pin sidebar arc")
    c.add("card.duplicate", "Duplicate card", CARDS, lambda: ui.duplicate_tab(), shortcuts=["Ctrl+Shift+K"],
          icon="copy", keywords="clone copy tab")
    c.add("card.next", "Focus next card", CARDS, lambda: ui.focus_adjacent(1, edge_add=True), shortcuts=["Alt+Right"],
          icon="chev_right", keywords="right step")
    c.add("card.prev", "Focus previous card", CARDS, lambda: ui.focus_adjacent(-1, edge_add=True),
          shortcuts=["Alt+Left"], icon="chev_left", keywords="left step")
    c.add("card.next_cycle", "Next card (wraps around)", CARDS, lambda: ui.focus_adjacent(1, wrap=True),
          shortcuts=["Ctrl+Tab"], icon="chev_right", palette=False)
    c.add("card.prev_cycle", "Previous card (wraps around)", CARDS, lambda: ui.focus_adjacent(-1, wrap=True),
          shortcuts=["Ctrl+Shift+Tab"], icon="chev_left", palette=False)
    c.add("card.move_right", "Move card right", CARDS, lambda: ui.move_card(1), shortcuts=["Alt+Shift+Right"],
          icon="forward", keywords="reorder")
    c.add("card.move_left", "Move card left", CARDS, lambda: ui.move_card(-1), shortcuts=["Alt+Shift+Left"],
          icon="back", keywords="reorder")
    for n in range(1, 9):
        c.add(f"card.goto{n}", f"Go to card {n}", CARDS, lambda i=n - 1: ui.goto_index(i),
              shortcuts=[f"Ctrl+{n}"], palette=False)
    c.add("card.goto_last", "Go to last card", CARDS, lambda: ui.goto_index(-1), shortcuts=["Ctrl+9"], palette=False)
    c.add("card.select_all", "Select all cards", CARDS, ui.select_all_cards, shortcuts=["Ctrl+Shift+A"],
          icon="selectall", keywords="multi select")
    c.add("card.sleep", "Put card to sleep", CARDS, lambda: ui.sleep_tab(), icon="moon",
          keywords="hibernate memory saver discard")
    c.add("card.sleep_inactive", "Sleep all inactive cards now", CARDS,
          lambda: ui.toast(f"Checked {ctx.lifecycle.sleep_inactive_now()} card(s) for sleep", "moon"), icon="moon",
          keywords="memory saver hibernate")
    c.add("card.wake_all", "Wake all cards in this space", CARDS, lambda: ctx.lifecycle.wake_all(
        ctx.state.active_space_id), icon="sun", keywords="restore")
    c.add("card.mute", "Mute / unmute card", CARDS, lambda: ui.toggle_mute(), shortcuts=["Ctrl+M"], icon="mute",
          keywords="audio sound volume")
    c.add("card.screenshot", "Copy card screenshot", CARDS, lambda: ui.copy_screenshot(),
          shortcuts=["Ctrl+Shift+S"], icon="crop", keywords="capture image")
    c.add("card.copy_url", "Copy page address", CARDS, ui.copy_url, shortcuts=["Ctrl+Shift+C"], icon="link",
          keywords="url clipboard")
    c.add("card.copy_clean_url", "Copy link without trackers", CARDS, lambda: ui.copy_clean_link(), icon="link",
          keywords="clean url utm fbclid share clipboard")
    c.add("card.open_external", "Open page in default browser", CARDS, ui.open_external, icon="newwindow")

    # ---------------------------------------------------------------- layout
    LAYOUT = "Canvas & layout"
    for n in range(1, 10):
        c.add(f"layout.scale{n}", f"Scale card(s) to {n * 10}%", LAYOUT, lambda f=n / 10: ui.scale_selected(f),
              shortcuts=[f"Alt+{n}"], icon="columns", keywords=f"width resize {n}0 percent")
    c.add("layout.scale10", "Scale card(s) to 100% (full width)", LAYOUT, lambda: ui.scale_selected(1.0),
          shortcuts=["Alt+0"], icon="fullscreen", keywords="width resize full 100 percent")
    c.add("layout.split2", "Split view 50 / 50", LAYOUT, lambda: ui.split(2), shortcuts=["Alt+Shift+D"],
          icon="columns", keywords="dual side by side two")
    c.add("layout.split3", "Triple columns 33 / 33 / 33", LAYOUT, lambda: ui.split(3), shortcuts=["Alt+Shift+T"],
          icon="tiles", keywords="three thirds")
    c.add("layout.split4", "Quad columns 25% × 4", LAYOUT, lambda: ui.split(4), shortcuts=["Alt+Shift+Q"],
          icon="grid", keywords="four quarters")
    c.add("layout.focus80", "Focus view 80%", LAYOUT, lambda: ui.scale_selected(0.8), icon="fullscreen",
          keywords="focus wide")
    c.add("layout.full_toggle", "Toggle full width for card", LAYOUT,
          lambda: ui.toggle_full_width(ctx.state.active_tab.id) if ctx.state.active_tab else None, icon="fullscreen")
    c.add("layout.minimap", "Canvas overview strip", LAYOUT, lambda: s.toggle("canvas.show_minimap"), icon="grid",
          state=on_off("canvas.show_minimap"), keywords="minimap")

    # ------------------------------------------------------------ navigation
    NAV = "Navigation"
    c.add("nav.back", "Back", NAV, lambda: ui.nav("back"), shortcuts=["Ctrl+[", "Back"], icon="back")
    c.add("nav.forward", "Forward", NAV, lambda: ui.nav("forward"), shortcuts=["Ctrl+]", "Forward"], icon="forward")
    c.add("nav.reload", "Reload", NAV, lambda: ui.nav("reload"), shortcuts=["F5", "Ctrl+R", "Refresh"],
          icon="refresh")
    c.add("nav.hard_reload", "Hard reload (bypass cache)", NAV, lambda: ui.nav("hard_reload"),
          shortcuts=["Ctrl+F5", "Ctrl+Shift+R", "Shift+F5"], icon="refresh", keywords="force cache")
    c.add("nav.stop", "Stop loading", NAV, lambda: ui.nav("stop"), icon="stop")
    c.add("nav.home", "Home", NAV, lambda: ui.go_home(), shortcuts=["Alt+Home"], icon="home",
          keywords="start page homepage")

    # ------------------------------------------------------------------ page
    PAGE = "Page"
    c.add("page.find", "Find in page", PAGE, ui.find_in_page, shortcuts=["Ctrl+F"], icon="search",
          keywords="search text")
    c.add("page.zoom_in", "Zoom in", PAGE, lambda: ui.zoom(1), shortcuts=["Ctrl+=", "Ctrl++"], icon="zoom_in")
    c.add("page.zoom_out", "Zoom out", PAGE, lambda: ui.zoom(-1), shortcuts=["Ctrl+-"], icon="zoom_out")
    c.add("page.zoom_reset", "Reset zoom", PAGE, lambda: ui.zoom(0), shortcuts=["Ctrl+0"], icon="zoom_in")
    c.add("page.devtools", "Developer tools", PAGE, ui.toggle_devtools, shortcuts=["F12", "Ctrl+Shift+I"],
          icon="code", keywords="inspect inspector console devtools")
    c.add("page.view_source", "View page source", PAGE, ui.view_source, shortcuts=["Ctrl+U"], icon="code")
    c.add("page.print", "Print…", PAGE, lambda: ui.print_card(), shortcuts=["Ctrl+P"], icon="print")
    c.add("page.save", "Save page as…", PAGE, ui.save_page, shortcuts=["Ctrl+S"], icon="save", keywords="download")
    c.add("page.pdf", "Save page as PDF…", PAGE, ui.save_pdf, icon="save", keywords="export pdf")
    c.add("page.bookmark", "Bookmark / unbookmark page", PAGE, lambda: ui.toggle_bookmark(), shortcuts=["Ctrl+D"],
          icon="star", keywords="favorite star")
    c.add("page.clear_site_data", "Clear this site's data", PAGE, lambda: ui.clear_site_data(), icon="clear",
          keywords="cookies storage reset site")

    # ---------------------------------------------------------------- spaces
    SPACES = "Spaces"
    c.add("space.next", "Next space", SPACES, lambda: ui.switch_space(1), shortcuts=["Alt+Down"], icon="chev_down",
          keywords="workspace switch")
    c.add("space.prev", "Previous space", SPACES, lambda: ui.switch_space(-1), shortcuts=["Alt+Up"], icon="chev_up",
          keywords="workspace switch")
    c.add("space.new", "New space…", SPACES, lambda: ui.new_space(False), shortcuts=["Ctrl+N"], icon="people",
          keywords="workspace profile")
    c.add("space.new_incognito", "New incognito space", SPACES, lambda: ui.new_space(True),
          shortcuts=["Ctrl+Shift+N"], icon="incognito", keywords="private off the record")
    c.add("space.edit", "Edit current space…", SPACES, lambda: ui.edit_space(), icon="edit",
          keywords="rename icon color")
    c.add("space.delete", "Delete current space…", SPACES, lambda: ui.delete_space(), icon="delete")
    c.add("space.focus", "Focus space list (↑ / ↓ to switch)", SPACES, lambda: ui.window.sidebar.focus_spaces(),
          shortcuts=["Ctrl+Shift+E"], icon="people")
    c.add("space.proxy", "Proxy for current space…", SPACES, lambda: ui.set_space_proxy(), icon="vpn")

    # ------------------------------------------------------------------ view
    VIEW = "View"
    c.add("view.toggle_sidebar", "Toggle sidebar", VIEW, ui.toggle_sidebar, shortcuts=["Ctrl+B"], icon="sidebar")
    c.add("view.toggle_favorites", "Toggle bookmarks bar", VIEW, ui.toggle_favorites_bar,
          shortcuts=["Ctrl+Shift+B"], icon="bookmarks", keywords="favorites bar",
          state=on_off("appearance.favorites_bar"))
    c.add("view.toggle_home", "Home button on the ribbon", VIEW, lambda: s.toggle("toolbar.home_button"),
          icon="home", state=on_off("toolbar.home_button"), keywords="toolbar start page")
    c.add("view.toggle_animations", "Fluid animations", VIEW, ui.toggle_animations, icon="lightning",
          keywords="motion transitions reduce", state=on_off("appearance.animations"))
    c.add("view.theme_dark", "Theme: dark", VIEW, lambda: ui.set_theme("dark"), icon="moon")
    c.add("view.theme_light", "Theme: light", VIEW, lambda: ui.set_theme("light"), icon="sun")
    c.add("view.theme_system", "Theme: follow Windows", VIEW, lambda: ui.set_theme("system"), icon="settings")
    for mat, label in (("mica", "Mica"), ("mica_alt", "Mica Alt"), ("acrylic", "Acrylic"), ("solid", "Solid")):
        c.add(f"view.material_{mat}", f"Window material: {label}", VIEW, lambda m=mat: ui.set_material(m),
              icon="tiles", keywords="backdrop glass transparency blur")
    c.add("view.fullscreen", "Full screen", VIEW, ui.toggle_window_fullscreen, shortcuts=["F11"], icon="fullscreen")
    c.add("view.hotkeys", "Keyboard shortcuts", VIEW, ui.open_hotkeys, shortcuts=["Ctrl+/", "F1"], icon="keyboard",
          keywords="help cheat sheet hotkeys")
    c.add("view.force_dark_web", "Force dark mode on web pages", VIEW, lambda: s.toggle("appearance.force_dark_web"),
          icon="moon", state=on_off("appearance.force_dark_web"))

    # ----------------------------------------------------------------- tools
    TOOLS = "Tools"
    c.add("downloads.show", "Downloads", TOOLS, lambda: ui.open_dialog("downloads"), shortcuts=["Ctrl+J"],
          icon="download")
    c.add("history.show", "History", TOOLS, lambda: ui.open_dialog("history"), shortcuts=["Ctrl+H"], icon="history")
    c.add("bookmarks.show", "Bookmarks manager", TOOLS, lambda: ui.open_dialog("bookmarks"),
          shortcuts=["Ctrl+Shift+O"], icon="bookmarks", keywords="favorites")
    c.add("passwords.show", "Password manager", TOOLS, lambda: ui.open_dialog("passwords"), icon="key",
          keywords="logins credentials vault")
    c.add("settings.show", "Settings", TOOLS, lambda: ui.open_settings(), shortcuts=["Ctrl+,"], icon="settings",
          keywords="preferences options")
    from jbrowser.ui.dialogs.settings import PAGES
    for key, label, glyph in PAGES:
        if key != "general":
            c.add(f"settings.page_{key}", f"Settings: {label}", TOOLS, lambda k=key: ui.open_settings(k),
                  icon=glyph, keywords="preferences options")
    c.add("cookies.show", "Cookies manager", TOOLS, lambda: ui.open_dialog("cookies"), icon="fingerprint")
    c.add("permissions.show", "Site permissions", TOOLS, lambda: ui.open_dialog("permissions"), icon="permissions",
          keywords="camera microphone location notifications")
    c.add("userscripts.show", "User scripts & styles", TOOLS, lambda: ui.open_dialog("userscripts"), icon="code",
          keywords="inject css js greasemonkey")

    # --------------------------------------------------------------- privacy
    PRIV = "Privacy & security"
    c.add("privacy.clear_data", "Clear browsing data…", PRIV, lambda: ui.open_dialog("clear_data"),
          shortcuts=["Ctrl+Shift+Del"], icon="clear", keywords="history cache cookies delete")
    c.add("privacy.clear_cache", "Clear cache (all spaces)", PRIV,
          lambda: (ctx.profiles.clear_cache(), ui.toast("HTTP cache cleared for all spaces", "clear")), icon="clear")
    c.add("privacy.clear_cache_space", "Clear cache (current space)", PRIV,
          lambda: (ctx.profiles.clear_cache(ctx.state.active_space_id), ui.toast("Cache cleared", "clear")),
          icon="clear")
    c.add("privacy.clear_cookies_space", "Delete cookies (current space)", PRIV,
          lambda: (ctx.cookies.delete_all(ctx.state.active_space_id), ui.toast("Cookies deleted", "clear")),
          icon="delete")
    c.add("privacy.clear_history", "Clear all history", PRIV,
          lambda: (ctx.history.clear(), ui.toast("History cleared", "history")), icon="history")
    c.add("privacy.toggle_trackers", "Tracker & ad blocking", PRIV, lambda: s.toggle("privacy.block_trackers"),
          icon="shield", state=on_off("privacy.block_trackers"), keywords="adblock privacy shield")
    c.add("privacy.toggle_3pc", "Block third-party cookies", PRIV,
          lambda: s.toggle("privacy.block_third_party_cookies"), icon="fingerprint",
          state=on_off("privacy.block_third_party_cookies"))
    c.add("privacy.toggle_https", "Always try secure (HTTPS) connections", PRIV,
          lambda: s.toggle("privacy.https_upgrade"), icon="lock", state=on_off("privacy.https_upgrade"),
          keywords="https first upgrade")
    c.add("privacy.toggle_threats", "Phishing and malware protection", PRIV,
          lambda: s.toggle("privacy.threat_protection"), icon="warning", state=on_off("privacy.threat_protection"),
          keywords="safe browsing dangerous scam")
    c.add("privacy.toggle_fingerprint", "Fingerprinting protection", PRIV,
          lambda: s.toggle("privacy.fingerprint_protection"), icon="fingerprint",
          state=on_off("privacy.fingerprint_protection"), keywords="canvas webgl anti tracking")
    c.add("privacy.toggle_strip", "Remove tracking codes from links", PRIV, lambda: s.toggle("privacy.strip_tracking"),
          icon="link", state=on_off("privacy.strip_tracking"), keywords="utm fbclid gclid query parameters")
    c.add("privacy.site_info", "Site information and permissions", PRIV, ui.show_site_info_anchored, icon="info",
          keywords="lock padlock certificate security permissions")
    c.add("privacy.forget_site", "Forget this site", PRIV, ui.forget_current_site, icon="delete",
          keywords="remove history cookies erase")
    c.add("privacy.update_blocklist", "Update tracker blocklists", PRIV,
          lambda: (ctx.privacy.update_blocklist(), ui.toast("Downloading tracker lists", "sync")), icon="sync")
    c.add("privacy.update_threats", "Update phishing and malware list", PRIV,
          lambda: (ctx.threats.refresh(), ui.toast("Downloading the dangerous-site list", "sync")), icon="sync")

    # --------------------------------------------------------------- network
    NET = "Network"
    for mode, info in DNS_MODES.items():
        c.add(f"dns.{mode}", f"DNS: {info['label']}", NET, lambda m=mode: ui.set_dns(m), icon="network",
              keywords="resolver doh secure dns",
              state=lambda m=mode: "Active" if s.get("network.dns_mode") == m else None)
    c.add("proxy.toggle", "Toggle proxy", NET, ui.toggle_proxy, icon="vpn", state=lambda: ctx.proxy.description)
    c.add("proxy.settings", "Proxy settings…", NET, lambda: ui.open_dialog("proxy"), icon="vpn",
          keywords="http https socks5")
    c.add("dev.hosts", "Localhost developer mapping…", NET, lambda: ui.open_dialog("devhosts"), icon="developer",
          keywords="dev hosts ports .test")
    for port, desc in DEV_PORTS:
        c.add(f"dev.open{port}", f"Open localhost:{port}", NET, lambda p=port: ui.open_localhost(p), icon="connect",
              keywords=f"dev server {desc}")

    # ----------------------------------------------------------- performance
    PERF = "Performance"
    for pid, (label, _m) in SLEEP_PRESETS.items():
        c.add(f"perf.sleep_{pid}", f"Memory saver: {label}", PERF, lambda p=pid: ui.set_sleep_preset(p),
              icon="speed", keywords="tab sleeping hibernate",
              state=lambda p=pid: "Active" if s.get("performance.sleep_preset") == p else None)
    c.add("perf.throttle", "Throttle cards out of view", PERF, lambda: s.toggle("performance.throttle"),
          icon="speed", state=on_off("performance.throttle"), keywords="cpu gpu background render")

    # ------------------------------------------------------------------- app
    APP = "App"
    c.add("app.about", "About JBrowser", APP, lambda: ui.open_settings("about"), icon="info")
    c.add("app.welcome", "Replay the welcome tour", APP, lambda: ui.window.start_onboarding(replay=True),
          icon="lightbulb", keywords="onboarding setup intro tutorial guide")
    c.add("app.restart", "Restart JBrowser", APP, ui.restart, icon="sync", keywords="relaunch reload app")
    c.add("app.check_updates", "Check for updates", APP, ui.check_for_updates, icon="download",
          keywords="upgrade new version release github")
    c.add("app.reset_settings", "Reset settings to defaults…", APP, ui.reset_settings, icon="sync",
          keywords="restore default preferences")
    c.add("app.factory_reset", "Factory reset (erase everything)…", APP, ui.factory_reset, icon="delete",
          keywords="wipe erase hard reset clean install")
    c.add("app.quit", "Exit JBrowser", APP, lambda: ui.window.close() or QApplication.quit(),
          shortcuts=["Ctrl+Shift+Q"], icon="power")
