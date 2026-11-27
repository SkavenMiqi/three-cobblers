"""Length targets for the visible assistant reply in a conversation."""

MODES = (
    ('精简', '直接给结论，只留最必要的信息；一般不超过80字。'),
    ('适度', '给出结论和关键理由或步骤；一般80–200字。'),
    ('正等', '完整回答并交代必要背景和步骤；一般200–500字。'),
    ('详细', '按需解释依据、步骤、示例和注意点；复杂问题可用500–1000字。'),
)
DEFAULT_MODE = 2


def output_instruction(mode):
    name, guidance = MODES[mode]
    return (f'\n当前对话的输出模式：{name}。{guidance}'
            '字数是可见回复正文的大致目标，不必凑字或重复。用户明确指定篇幅时优先遵从；'
            '代码、必要警示和结构化工具数据不要为了字数截断。')
