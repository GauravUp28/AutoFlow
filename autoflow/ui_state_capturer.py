def capture_screenshot(page, filename):
    """Robust screenshot capture that tolerates closed pages/contexts."""
    try:
        if page.is_closed():
            print(f"[yellow]Skipped screenshot (page closed): {filename}[/yellow]")
            return False
        page.screenshot(path=filename)
        return True
    except Exception as e:
        print(f"[yellow]Screenshot failed for {filename}: {e}[/yellow]")
        return False
