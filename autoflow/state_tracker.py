import time
from PIL import Image
import io
import hashlib

def get_dom_snapshot(page):
    return page.content()

def get_visual_snapshot(page):
    return page.screenshot()

def detect_ui_change(page, prev_dom_hash=None, prev_img_hash=None):
    """Detect if the UI has changed by comparing DOM and visual hashes."""
    dom = page.content()
    img = page.screenshot()
    
    dom_hash = hashlib.md5(dom.encode()).hexdigest()
    img_hash = hashlib.md5(img).hexdigest()
    
    if prev_dom_hash and prev_img_hash:
        if dom_hash != prev_dom_hash or img_hash != prev_img_hash:
            return True, dom_hash, img_hash
        return False, dom_hash, img_hash
    
    return True, dom_hash, img_hash

def wait_for_ui_change(page, timeout=10):
    dom_before = get_dom_snapshot(page)
    img_before = get_visual_snapshot(page)
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(1)
        dom_after = get_dom_snapshot(page)
        img_after = get_visual_snapshot(page)
        if dom_after != dom_before or img_after != img_before:
            return True
    return False
