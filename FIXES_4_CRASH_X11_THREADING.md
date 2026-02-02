# FIXES_4_CRASH_X11_THREADING.md

## CONTEXT (READ FIRST)

Проект стабильно падает с **Segmentation fault** сразу после первого исправления слова:

```
Correcting: 'ghbdtn' → 'привет'
Segmentation fault
```

Падает:

* на NAS
* на рабочей машине
* одинаково

Это **НЕ логическая ошибка** и **НЕ тесты**.
Это **C-level crash** (Xlib / ctypes / Qt threading).

## ROOT CAUSE (ALREADY CONFIRMED)

❌ **X11 / layout switching вызывается НЕ из main (UI) thread**

Xlib **НЕ thread-safe**.
Любые вызовы `Xkb*`, `XLockGroup`, `XGetState`, `setxkbmap`, `xkb-switch`:

* из daemon thread
* из XRecord listener
* из Timer thread

→ **гарантированный segfault**, который:

* НЕ ловится try/except
* НЕ логируется
* НЕ ловится тестами

Все текущие `try/except` вокруг layout_switch — **бесполезны** и создают ложное ощущение безопасности.

---

## ABSOLUTE RULE (NO DISCUSSION)

> ❗️ **НИ ОДНА функция, трогающая X11 / layout / Qt,
> НЕ ИМЕЕТ ПРАВА вызываться вне main Qt thread.**

НАРУШЕНИЕ = SEGFAULT.

---

## REQUIRED ARCHITECTURE CHANGE (MANDATORY)

### 1. 🔥 УБРАТЬ layout switching ИЗ daemon ПОЛНОСТЬЮ

daemon.py:

* ❌ НЕ импортирует `layout_switch`
* ❌ НЕ вызывает `detect_target_layout`
* ❌ НЕ вызывает `switch_to_corrected_layout`
* ❌ НЕ трогает X11 / subprocess / ctypes вообще

daemon — **pure logic only**.

---

### 2. ✅ ВВЕСТИ HANDOFF-MECHANISM (SINGLE SOURCE OF TRUTH)

daemon **ТОЛЬКО сообщает НАМЕРЕНИЕ**, например:

```python
self._requested_layout = "ru" | "us" | None
self._layout_request_reason = "word" | "phrase" | "polish"
```

или через очередь / signal-safe структуру.

**daemon НЕ ДЕЛАЕТ layout switch. НИКОГДА.**

---

### 3. ✅ ВСЕ layout switch — ТОЛЬКО В Qt main thread

tray / main Qt app:

* по таймеру или сигналу:

  * проверяет `_requested_layout`
  * если есть — **В MAIN THREAD**:

    * вызывает `layout_switch.*`
    * логирует результат
    * очищает запрос

Qt thread = **единственное место**, где можно:

* Xlib
* setxkbmap
* xkb-switch
* ctypes

---

## HARD REQUIREMENTS (NON-NEGOTIABLE)

### A. Zero X11 calls outside UI thread

* grep по проекту:

  * `Xlib`
  * `Xkb`
  * `setxkbmap`
  * `xkb-switch`
  * `ctypes`

❌ если найдено в daemon / worker / timer → FIX REQUIRED

---

### B. Tests must reflect REALITY

Добавить тест:

* `test_no_layout_switch_in_daemon.py`
* assert:

  * daemon НЕ импортирует `layout_switch`
  * daemon НЕ содержит X11 symbols

(это архитектурный тест, не unit)

---

### C. Temporary sanity check (MANDATORY)

На первом этапе:

* полностью закомментировать layout switching
* убедиться:

  * segfault **ИСЧЕЗ ПОЛНОСТЬЮ**

Если падает дальше — значит искать **второй C-extension bug**.

---

## OUT OF SCOPE (DO NOT TOUCH)

* spell correction logic
* phrase logic
* polish logic
* UI cosmetics
* model selection

Фокус **ТОЛЬКО**:

* crash
* threading
* X11 safety

---

## ACCEPTANCE CRITERIA (STRICT)

1. `kautoswitch`:

   * НЕ падает после первого исправления
   * НЕ падает после 100 исправлений подряд

2. layout switching:

   * работает
   * вызывается ТОЛЬКО из Qt main thread

3. grep-проверка:

   * daemon.py НЕ содержит X11 / layout code

4. manual test:

   * `ghbdtn ` → `привет ` (с пробелом)
   * дальше печать продолжается без краша

---

## FINAL WARNING (READ CAREFULLY)

Если после этого изменения:

* layout switch снова будет вызван из daemon
* или из timer thread
* или из listener thread

→ проект **ВСЕГДА** будет нестабилен, независимо от количества тестов.

---

## DELIVERABLES

* архитектурный рефактор
* 1–2 теста, фиксирующих правило
* короткое README section:
  **“Why layout switching is UI-thread only”**

---

**СДЕЛАЙ ЭТО.
НЕ ИМПРОВИЗИРУЙ.
НЕ ПЫТАЙСЯ ЧИНИТЬ try/except.**
