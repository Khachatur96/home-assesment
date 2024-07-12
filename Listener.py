import asyncio
import sys
import os
import termios
import tty


class Listener:
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.stop_event = asyncio.Event()
        self.old_settings = None

    async def start(self):
        try:
            # Clear any pending input
            self._clear_input()

            # Disable terminal echo
            self._disable_echo()

            # Move cursor to the last line and print prompt
            self._print_prompt()

            prompt = await asyncio.wait_for(
                self.loop.run_in_executor(None, self._get_input),
                timeout=None
            )
            return prompt
        except asyncio.CancelledError:
            return None
        finally:
            # Re-enable terminal echo
            self._enable_echo()

    def _clear_input(self):
        import fcntl
        fd = sys.stdin.fileno()
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        try:
            sys.stdin.read()
        except:
            pass
        finally:
            fcntl.fcntl(fd, fcntl.F_SETFL, flags)

    def _disable_echo(self):
        fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(fd)
        tty.setraw(fd)

    def _enable_echo(self):
        if self.old_settings:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_settings)

    def _print_prompt(self):
        rows, _ = os.get_terminal_size()
        print(f"\033[{rows};0H", end='')
        print("\033[K", end='')
        print("Prompt: ", end='', flush=True)

    def _get_input(self):
        prompt = []
        while not self.stop_event.is_set():
            char = sys.stdin.read(1)
            if char == '\r':  # Enter key
                print()  # Move to next line after Enter
                return ''.join(prompt)
            elif char == '\x7f':  # Backspace
                if prompt:
                    prompt.pop()
                    print("\b \b", end='', flush=True)  # Erase character
            elif char:
                prompt.append(char)
                print(char, end='', flush=True)  # Echo the character
        return None

    async def stop(self):
        self.stop_event.set()
        print()
