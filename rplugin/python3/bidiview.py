import re
from typing import List

import pynvim


def to_bidi(text: str) -> str:
    """
    Find all farsi sections and reverse them
    keep the non farsi parts unchanged

    example:
        from this:
            '<p>یک متن فارسی و english قاطی در یک html است.</p>'
        to this:
            '<p>کی نتم یسراف و english یطاق رد کی html تسا.</p>'
    """

    pattern = "([\u0600-\u06FF|‌]+)"
    return re.sub(pattern, lambda match: match.group(1)[::-1], text)


def _bidi(lines: List[str]) -> List[str]:
    return [to_bidi(line) for line in lines]


@pynvim.plugin
class BidiView:
    def __init__(self, nvim):
        self.nvim = nvim
        self.bid = -1
        self.view_wid = -1
        self.view_bid = -1
        self.view_wnr = -1
        self.wid = self.nvim.call("win_getid")

    def _print(self, text: str) -> None:
        self.nvim.command(f"echom '{text}'")

    @property
    def view_valid(self) -> bool:
        """Check if the bidi view is still valid"""
        if self.view_wid == -1:
            return False
        return (
            self.nvim.call("nvim_win_is_valid", self.view_wid)
            and self.nvim.call("nvim_buf_is_valid", self.view_bid)
            and self.nvim.call("nvim_win_is_valid", self.wid)
            and self.nvim.call("nvim_buf_is_valid", self.bid)
        )

    def _set_view_text(self, text: List[str]) -> None:
        """Set bidi view text"""
        return self.nvim.call(
            "nvim_buf_set_lines",
            self.view_bid,
            0,
            -1,
            False,
            _bidi(text),
        )

    def _read_text(self) -> List[str]:
        """Read source buffer text"""
        return self.nvim.call("nvim_buf_get_lines", self.bid, 0, -1, False)

    def _set_view_modifiable(self, modifiable: bool) -> None:
        """Make bidi view unmodifiable"""
        self.nvim.call(
            "nvim_buf_set_option", self.view_bid, "modifiable", modifiable
        )

    def _update_view(self) -> None:
        """Set bidi view text"""
        lines = self._read_text()
        self._set_view_modifiable(True)
        self._set_view_text(lines)
        self._set_view_modifiable(False)

    def _set_window_binds(self, wid: int = None) -> None:
        if not wid:
            self.nvim.command("set scrollbind")
            self.nvim.command("set cursorbind")
            return

        self.nvim.call("nvim_win_set_option", wid, "scrollbind", True)
        self.nvim.call("nvim_win_set_option", wid, "cursorbind", True)
        return

    def _unset_window_binds(self, wid: int = None) -> None:
        if not wid:
            self.nvim.command("set noscrollbind")
            self.nvim.command("set nocursorbind")
            return

        self.nvim.call("nvim_win_set_option", wid, "noscrollbind", True)
        self.nvim.call("nvim_win_set_option", wid, "nocursorbind", True)
        return

    def _multi_dig(self):
        """
        Check if character under cursor has multiple digraphs

        example:
        ascii command output when cursor is on a phrase like 'لا' is like this:
        <ﻝ> 1604, Hex 0644, Oct 3104, Digr l+ <ﺍ> 1575, Hex 0627, Oct 3047, Digr a+

        more info:
            https://neovim.io/doc/user/digraph.html#digraphs
        """

        p = "<.*> +([0-9]+)"
        character_info = self.nvim.command_output("ascii")
        char_dec = re.search(p, character_info)
        if char_dec:
            char_dec = int(char_dec.group(1))
            if 1548 <= char_dec <= 1785:
                return True
        return False

    def _highlight_cursor(self) -> None:
        self.nvim.call(
            "nvim_buf_clear_namespace",
            self.view_bid,
            0,
            0,
            -1,
        )
        cursor_pos_y, cursor_pos_x = self.nvim.call(
            "nvim_win_get_cursor", self.wid
        )

        if cursor_pos_y != 0:
            cursor_pos_y -= 1

        end_cursor_pos_x = cursor_pos_x
        if self._multi_dig():
            end_cursor_pos_x += 2
        else:
            end_cursor_pos_x += 1

        self.nvim.call(
            "nvim_buf_add_highlight",
            self.view_bid,
            0,
            "Error",
            cursor_pos_y,
            cursor_pos_x,
            end_cursor_pos_x,
        )

    def _create_view_buf(self) -> int:
        return self.nvim.call("nvim_create_buf", True, True)

    def _set_view_name(self) -> None:
        """Set bidi view name, filetype"""

        buf_name = self.nvim.call("bufname", self.bid)
        view_buf_name = f"bidi-{buf_name}"
        self.nvim.call("nvim_buf_set_name", self.view_bid, view_buf_name)

        buf_filetype = self.nvim.call(
            "nvim_buf_get_option", self.bid, "filetype"
        )
        self.nvim.call(
            "nvim_buf_set_option", self.view_bid, "filetype", buf_filetype
        )

    def _init_view(self) -> None:
        """
        Split current window, attach bidi view buffer to new window
        update bidi view text, set view window binds
        """

        self._set_window_binds()
        self.wid = self.nvim.call("win_getid")
        self.view_bid = self._create_view_buf()
        self.bid = self.nvim.call("nvim_buf_get_number", 0)
        self.view_wnr = self.nvim.command("sp")
        self.view_wid = self.nvim.call("win_getid", self.view_wnr)

        self.nvim.call("nvim_win_set_buf", self.view_wid, self.view_bid)
        self._update_view()
        self._set_window_binds(wid=self.view_wid)
        self._highlight_cursor()
        self._set_view_name()

    @pynvim.autocmd("TextChanged", "*")
    def on_textchanged(self, *args):
        if self.view_valid:
            self._update_view()

    @pynvim.autocmd("TextChangedI", "*")
    def on_textchangedi(self, *args):
        if self.view_valid:
            self._update_view()

    @pynvim.autocmd("CursorMoved", "*")
    def highlight_cursor(self, *args):
        if not self.nvim.call("win_getid") == self.wid:
            return
        if self.view_valid:
            self._highlight_cursor()

    @pynvim.autocmd("BufHidden", "*")
    def on_close(self, *args):
        self.hide_bidi_view()

    @pynvim.command("ShowBidiView")
    @pynvim.function("ShowBidiView")
    def show_bidi_view(self, *args):
        if not self.view_valid:
            self._init_view()
            self.nvim.call("nvim_set_current_win", self.wid)
            self.nvim.command("syncbind")

    @pynvim.command("HideBidiView")
    @pynvim.function("HideBidiView")
    def hide_bidi_view(self, *args):
        try:
            self._unset_window_binds(wid=self.view_wid)
            self.nvim.command(f"bwipeout {self.view_bid}")
            self.nvim.call("nvim_win_close", 0, True)
        except Exception as e:
            self.nvim.err_write(str(e))
        finally:
            self.view_wid = -1
