try:
 import pyautogui
except ImportError: pyautogui=None
def _need():
 if pyautogui is None: raise RuntimeError("Install pyautogui for GUI support")
def get_screen_size(): _need(); return {"width":pyautogui.size().width,"height":pyautogui.size().height}
def take_screenshot(path="screen.png"): _need(); pyautogui.screenshot(path); return {"path":path}
def move_mouse(x,y): _need(); pyautogui.moveTo(x,y)
def click_mouse(x,y,clicks=1): _need(); pyautogui.click(x,y,clicks=clicks)
def double_click(x,y): click_mouse(x,y,2)
def scroll(amount): _need(); pyautogui.scroll(amount)
def type_keyboard(text): _need(); pyautogui.write(text)
def press_key(key): _need(); pyautogui.press(key)
