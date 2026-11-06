"""Drawn role icons, independent of emoji/font availability on Android."""
from kivy.uix.button import Button
from kivy.properties import StringProperty
from kivy.graphics import Color, Line, Ellipse
from kivy.metrics import dp


class RoleButton(Button):
    role = StringProperty('mouth')

    def __init__(self, **kwargs):
        super().__init__(text='', background_normal='', background_color=(0, 0, 0, 0),
                         size_hint_x=None, width=dp(64), **kwargs)
        self.bind(pos=self.draw, size=self.draw, role=self.draw, state=self.draw)
        self.draw()

    def draw(self, *_):
        self.canvas.after.clear()
        size = min(dp(24), self.height * .55)
        both = self.role == 'both'
        centers = [(self.center_x - size * .6, 'ear'), (self.center_x + size * .6, 'mouth')] if both else [(self.center_x, self.role)]
        with self.canvas.after:
            Color(0, 1, .8, .65 if self.state == 'down' else 1)
            for center, kind in centers:
                x, y = center - size / 2, self.center_y - size / 2
                def points(values):
                    return [coordinate for px, py in values for coordinate in (x + px * size, y + py * size)]
                if kind == 'ear':
                    Line(points=points([(.32,.08),(.52,.05),(.68,.18),(.69,.32),(.85,.51),(.88,.72),(.78,.91),(.58,.98),(.35,.95),(.16,.78),(.12,.56)]), width=dp(1.5), joint='round')
                    Line(points=points([(.32,.60),(.32,.73),(.43,.83),(.58,.82),(.68,.70),(.64,.57),(.47,.49),(.46,.33)]), width=dp(1.3), joint='round')
                else:
                    Line(points=points([(.04,.51),(.26,.72),(.40,.68),(.50,.77),(.61,.68),(.76,.72),(.96,.51),(.78,.25),(.50,.17),(.23,.25),(.04,.51)]), width=dp(1.4), joint='round')
                    Line(points=points([(.04,.51),(.28,.46),(.50,.49),(.74,.46),(.96,.51)]), width=dp(1.2))
