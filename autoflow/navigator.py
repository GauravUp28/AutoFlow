import asyncio
from typing import List, Optional
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from utils import to_ms

CTA_WORDS = ["create","new","add","save","submit","filter","settings","ok","continue","next","done"]

class Navigator:
    def __init__(self, headless: bool = True, cookies_path: Optional[str] = None):
        self.headless = headless; self.cookies_path = cookies_path
        self.playwright = None; self.browser: Optional[Browser] = None
        self.ctx: Optional[BrowserContext] = None; self.page: Optional[Page] = None
    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.ctx = await self.browser.new_context()
        if self.cookies_path:
            import json, pathlib
            try:
                data = json.loads(pathlib.Path(self.cookies_path).read_text(encoding="utf-8"))
                await self.ctx.add_cookies(data)
            except Exception: pass
        self.page = await self.ctx.new_page()
    async def stop(self):
        if self.ctx: await self.ctx.close()
        if self.browser: await self.browser.close()
        if self.playwright: await self.playwright.stop()
    async def goto(self, url: str):
        await self.page.goto(url, wait_until="domcontentloaded", timeout=to_ms(45))
    async def wait_possible_state_change(self, timeout_sec: float = 3.0):
        try: await self.page.wait_for_load_state("networkidle", timeout=to_ms(timeout_sec))
        except Exception: await asyncio.sleep(timeout_sec)
    async def click_semantic(self, keywords: List[str]) -> bool:
        kw = [k.lower() for k in keywords]
        for k in kw:
            try:
                loc = self.page.get_by_role("button", name=lambda n: n and k in n.lower())
                if await loc.count() > 0: await loc.first.click(); return True
            except Exception: pass
        for k in kw:
            try:
                loc = self.page.get_by_text(k, exact=False)
                if await loc.count() > 0: await loc.first.click(); return True
            except Exception: pass
        return await self.scan_and_click_cta()
    async def scan_and_click_cta(self) -> bool:
        for word in CTA_WORDS:
            try:
                loc = self.page.get_by_role("button", name=lambda n: n and word in n.lower())
                if await loc.count() > 0: await loc.first.click(); return True
            except Exception: pass
        try:
            loc = self.page.locator("button, [role=button], a:visible")
            if await loc.count() > 0: await loc.first.click(); return True
        except Exception: pass
        return False
    async def type_into_likely_field(self, text: str) -> bool:
        try:
            focused = self.page.locator(":focus"); 
            if await focused.count() > 0: await focused.type(text); return True
        except Exception: pass
        try:
            tb = self.page.get_by_role("textbox")
            if await tb.count() > 0: await tb.first.click(); await tb.first.type(text); return True
        except Exception: pass
        return False
