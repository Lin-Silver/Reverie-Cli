"""Native window and input event pump for bounded Engine sessions."""
from __future__ import annotations


class NativeWindow:
    def __init__(self, profile, inputs):
        import pyglet
        self.closed = False
        self.inputs = inputs
        config = pyglet.gl.Config(double_buffer=True, major_version=3, minor_version=3)
        self.window = pyglet.window.Window(profile.width, profile.height, caption=profile.title,
                                           resizable=True, vsync=True, config=config)
        self.window.push_handlers(
            on_close=self.on_close,
            on_key_press=lambda symbol, modifiers: inputs.on_key_press(symbol),
            on_key_release=lambda symbol, modifiers: inputs.on_key_release(symbol),
            on_mouse_press=lambda x, y, button, modifiers: inputs.on_mouse_press(button, x, y),
            on_mouse_release=lambda x, y, button, modifiers: inputs.on_mouse_release(button, x, y),
            on_mouse_motion=lambda x, y, dx, dy: inputs.on_mouse_motion(x, y),
            on_mouse_drag=lambda x, y, dx, dy, buttons, modifiers: inputs.on_mouse_motion(x, y),
            on_mouse_scroll=lambda x, y, sx, sy: inputs.on_mouse_scroll(sy),
            on_deactivate=self.release_inputs,
        )
        self.window.switch_to()

    def on_close(self):
        # Keep the GL context alive until the renderer releases its resources.
        self.closed = True
        return True

    def release_inputs(self):
        for symbol in list(self.inputs.keys_pressed):
            self.inputs.on_key_release(symbol)
        for button in list(self.inputs.mouse_buttons_pressed):
            self.inputs.on_mouse_release(button, *self.inputs.mouse_position)

    def pump(self):
        self.window.switch_to()
        previous = self.inputs.mouse_position
        self.window.dispatch_events()
        self.inputs.mouse_delta = (self.inputs.mouse_position[0] - previous[0],
                                   self.inputs.mouse_position[1] - previous[1])
        return not self.closed

    def size(self):
        return self.window.get_framebuffer_size()

    def flip(self):
        self.window.flip()

    def close(self):
        self.release_inputs()
        self.window.close()
        self.closed = True
