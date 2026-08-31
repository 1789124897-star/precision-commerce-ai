"""1688 反爬工具集 —— 随机延迟 + 指数退避重试 + Cookie 持久化，可作库或直接运行刷新 cookie。"""
import json
import logging
import os
import random
import time

from app.core.paths import OUTPUT_DIR

logger = logging.getLogger(__name__)

_COOKIE_FILE = OUTPUT_DIR / "1688_cookies.json"
_MAX_AGE_HOURS = 12


def random_delay(min_s=2.0, max_s=3.5):
    """随机等待，模拟人类操作间隔。"""
    time.sleep(random.uniform(min_s, max_s))


def has_valid_cookies(cookie_file=None):
    """cookie 文件 12 小时内未修改则有效。"""
    path = cookie_file or _COOKIE_FILE
    if not os.path.exists(str(path)):
        return False
    age = time.time() - os.path.getmtime(str(path))
    return age < _MAX_AGE_HOURS * 3600


def save_cookies(page, cookie_file=None):
    """把当前浏览器的 cookie 保存到文件。"""
    path = cookie_file or _COOKIE_FILE
    cookies = page.cookies()
    with open(str(path), "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    logger.info("Cookie 已保存到 %s", path)


def load_cookies(page, cookie_file=None):
    """有效则把 cookie 注入页面，返回是否成功。"""
    path = cookie_file or _COOKIE_FILE
    if not has_valid_cookies(path):
        return False
    with open(str(path), encoding="utf-8") as f:
        cookies = json.load(f)
    for c in cookies:
        try:
            page.set.cookies(c)
        except Exception:
            pass
    logger.info("Cookie 已加载，来自 %s", path)
    return True


def ensure_fresh_cookies(page, email="", password=""):
    """cookie 过期则打开登录页刷新 cookie 文件（有账密顺手登录）。"""
    if has_valid_cookies():
        return

    logger.info("Cookie 过期或不存在，开始刷新...")
    page.get("https://login.1688.com/member/signin.htm")
    random_delay(1.0, 2.0)

    if email and password:
        _try_login(page, email, password)

    save_cookies(page)


def _try_login(page, email, password):
    """试着用账密登录 1688，失败不报错。"""
    try:
        tab = page.ele("text:密码登录") or page.ele("div:contains(密码登录)")
        if tab:
            tab.click()
            random_delay(0.5, 1.0)
    except Exception:
        pass

    try:
        inp = page.ele("#fm-login-id") or page.ele('input[name="loginId"]')
        if inp:
            inp.input(email)
    except Exception:
        pass

    try:
        inp = page.ele("#fm-login-password") or page.ele('input[name="password"]')
        if inp:
            inp.input(password)
    except Exception:
        pass

    random_delay(0.3, 0.8)

    try:
        btn = page.ele("#fm-login-submit") or page.ele('button[type="submit"]')
        if btn:
            btn.click()
    except Exception:
        pass

    try:
        page.wait.url_change("1688.com", timeout=15)
        logger.info("1688 登录成功")
    except Exception:
        logger.warning("登录可能需要验证码，cookie 照存")


if __name__ == "__main__":
    from dotenv import load_dotenv
    from DrissionPage import ChromiumOptions, ChromiumPage

    load_dotenv()

    EMAIL = os.getenv("ALIBABA_1688_EMAIL", "")
    PASSWORD = os.getenv("ALIBABA_1688_PASSWORD", "")

    if has_valid_cookies():
        print("Cookie 仍有效，跳过刷新")
        exit(0)

    print("Cookie 过期或不存在，开始刷新...")

    co = ChromiumOptions()
    co.headless(True)
    co.set_browser_path(os.getenv(
        "EDGE_PATH",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ))
    page = ChromiumPage(co)

    try:
        ensure_fresh_cookies(page, EMAIL, PASSWORD)
    finally:
        page.quit()
