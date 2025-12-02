from pathlib import Path
import json
from playwright.async_api import Page
from utils import now_ts

class StateCapture:
    def __init__(self, page: Page, out_dir: Path):
        self.page = page; self.out_dir = out_dir; self.step = 0
    async def capture_state(self, event: str, info=None):
        idx = f"{self.step:02d}"; self.step += 1
        png = self.out_dir / f"{idx}_{event}.png"; meta = self.out_dir / f"{idx}_{event}.json"
        meta_obj = {"ts": now_ts(), "event": event, "url": self.page.url,
                    "title": await self.page.title(), "roles": await self._count_roles(),
                    "has_dialog": await self._has_dialog(), "toast_text": await self._get_toast_text(),
                    "info": info or {}}
        await self.page.screenshot(path=str(png), full_page=True)
        meta.write_text(json.dumps(meta_obj, indent=2), encoding="utf-8")
    async def _count_roles(self):
        roles = {}
        for role in ["button","textbox","dialog","combobox","menu","link","heading","alert"]:
            try: roles[role] = await self.page.get_by_role(role).count()
            except Exception: roles[role] = None
        return roles
    async def _has_dialog(self) -> bool:
        try: return (await self.page.get_by_role("dialog").count()) > 0
        except Exception: return False
    async def _get_toast_text(self):
        try:
            loc = self.page.get_by_role("alert")
            if await loc.count() > 0: return await loc.first.inner_text()
        except Exception: pass
        try:
            loc = self.page.locator("[class*='toast'], [class*='Toast'], [data-testid*='toast']")
            if await loc.count() > 0: return await loc.first.inner_text()
        except Exception: pass
        return None
