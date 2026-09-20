class Browser:
    def __init__(self): self.page=None; self._pw=None; self._browser=None
    async def start(self):
        from playwright.async_api import async_playwright
        self._pw=await async_playwright().start(); self._browser=await self._pw.chromium.launch(headless=True); self.page=await self._browser.new_page()
    async def close(self):
        if self._browser: await self._browser.close()
        if self._pw: await self._pw.stop()
    async def open_url(self,url): await self.page.goto(url); return {"url":self.page.url,"title":await self.page.title()}
    async def get_page_title(self): return await self.page.title()
    async def get_page_text(self): return await self.page.locator("body").inner_text()
    async def click(self,selector): await self.page.locator(selector).click(); return {"clicked":selector}
    async def fill(self,selector,text): await self.page.locator(selector).fill(text); return {"filled":selector}
    async def type_text(self,selector,text): await self.page.locator(selector).type(text); return {"typed":selector}
    async def press_key(self,selector,key): await self.page.locator(selector).press(key); return {"pressed":key}
    async def take_screenshot(self,path): await self.page.screenshot(path=path); return {"path":path}
    async def wait_for_element(self,selector,timeout=10000): await self.page.locator(selector).wait_for(timeout=timeout); return {"found":selector}
