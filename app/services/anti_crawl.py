"""1688 反爬工具集 —— 随机延迟 + 指数退避重试 + Cookie 持久化。

作为库被 scraper import，也可以直接运行刷新 cookie：
    python -m app.services.anti_crawl
"""
import json
import os
import random
import time
from pathlib import Path

# cookie 文件放在项目根目录
_COOKIE_FILE = Path(__file__).resolve().parent.parent.parent / "1688_cookies.json"
_MAX_AGE_HOURS = 12


# ═══════════════════════════════════════════════════════════════════
# 行为层
# ═══════════════════════════════════════════════════════════════════

def random_delay(min_s=2.0, max_s=3.5):
    """随机等一小段时间，模拟人类操作间隔。"""
    time.sleep(random.uniform(min_s, max_s))


# ═══════════════════════════════════════════════════════════════════
# 容错层
# ═══════════════════════════════════════════════════════════════════

def retry(func, max_retries=3):
    """重试包装器，指数退避：2s → 4s → 8s。"""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_error = e
            print("第 " + str(attempt) + " 次失败: " + str(e))
            if attempt < max_retries:
                wait = 2 ** attempt
                print("等 " + str(wait) + " 秒后重试...")
                time.sleep(wait)
    raise last_error


# ═══════════════════════════════════════════════════════════════════
# 登录态层
# ═══════════════════════════════════════════════════════════════════

def has_valid_cookies(cookie_file=None):
    """cookie 文件存在且 12 小时内没有过期。

    用文件修改时间（mtime）判断，不解析 cookie 内容。
    1688 的 cookie 经常设很短的过期时间，但实际还能用，
    所以用 mtime 比解析 expires 更靠谱。
    """
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
    print("Cookie 已保存到 " + str(path))


def load_cookies(page, cookie_file=None):
    """把之前存的 cookie 注入到当前页面。

    只在 cookie 有效时才加载，过期就不加载。
    返回 True 表示加载成功，False 表示没有有效 cookie。
    """
    path = cookie_file or _COOKIE_FILE
    if not has_valid_cookies(path):
        return False
    with open(str(path), "r", encoding="utf-8") as f:
        cookies = json.load(f)
    for c in cookies:
        try:
            page.set.cookies(c)
        except Exception:
            pass
    print("Cookie 已加载，来自 " + str(path))
    return True


def ensure_fresh_cookies(page, email="", password=""):
    """确保 cookie 文件是新鲜的。

    cookie 没过期 → 跳过。
    cookie 过期了 → 打开 1688 登录页拿新 cookie。
    有账密就顺手登录，登不上也不管，cookie 照存。

    核心目的不是登录，是刷新 cookie 文件，
    让后续 12 小时的爬取都能复用同样的身份标识。
    """
    if has_valid_cookies():
        return

    print("Cookie 过期或不存在，开始刷新...")
    page.get("https://login.1688.com/member/signin.htm")
    random_delay(1.0, 2.0)

    # 有账密就试登录，没有就只拿游客 cookie
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
        print("1688 登录成功")
    except Exception:
        print("登录可能需要验证码，不管了，cookie 照存")


# ═══════════════════════════════════════════════════════════════════
# 命令行入口：手动刷新 cookie
# ═══════════════════════════════════════════════════════════════════

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
