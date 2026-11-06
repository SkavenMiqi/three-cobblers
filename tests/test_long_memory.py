import unittest
from talkapp.storage import History
from talkapp.memory import parse_facts


class LongMemoryTests(unittest.TestCase):
    def setUp(self):
        self.h = History(':memory:')

    def tearDown(self):
        self.h.close()

    def turn(self, text, project_id=None):
        chat = self.h.create(project_id=project_id)
        user = self.h.append(chat, 'user', text)
        self.h.append(chat, 'assistant', '好的')
        job = next(item for item in self.h.memory_jobs() if item['source_id'] == user)
        return chat, user, job

    def fact(self, text, operation='set', category='user', key='residence'):
        return {'category': category, 'key': key, 'text': text, 'operation': operation}

    def test_cross_session_correction_forgetting_and_source_deletion(self):
        first, _, job = self.turn('我住北京')
        self.h.apply_memory(job, [self.fact('用户住北京')])
        second, _, new = self.turn('我现在搬到上海了')
        self.h.apply_memory(new, [self.fact('用户住上海')])
        current = self.h.create()
        self.assertEqual([v['text'] for v in self.h.long_memories(current)], ['用户住上海'])
        third, _, forget = self.turn('忘记我的住址')
        self.h.apply_memory(forget, [self.fact('', 'forget')])
        self.assertEqual(self.h.long_memories(current), [])
        self.h.delete(third)
        self.assertEqual(self.h.long_memories(current)[0]['text'], '用户住上海')
        self.h.delete(second)
        self.assertEqual(self.h.long_memories(current)[0]['text'], '用户住北京')

    def test_processed_once_and_branch_changes_exclude_abandoned_fact(self):
        chat, user, job = self.turn('喜欢简洁')
        self.h.apply_memory(job, [self.fact('喜欢简洁', key='style')])
        self.assertEqual(self.h.memory_jobs(), [])
        self.h.append(chat, 'user', '另一分支', parent=None)
        self.assertEqual(self.h.long_memories(self.h.create()), [])
        self.h.select(user)
        self.assertEqual(self.h.long_memories(chat)[0]['text'], '喜欢简洁')

    def test_project_facts_scoped_user_profile_global(self):
        chat, _, job = self.turn('我在做项目A，喜欢例子')
        self.h.apply_memory(job, [self.fact('项目A使用Python', category='project', key='language'),
                                  self.fact('喜欢例子', key='style')])
        other = self.h.create()
        self.assertEqual(len(self.h.long_memories(other)), 1)
        same = self.h.create(project_id=self.h.project(chat)['id'])
        self.assertEqual(len(self.h.long_memories(same)), 2)

    def test_invalid_json_is_not_successful_empty_extraction(self):
        with self.assertRaises(ValueError):
            parse_facts('I cannot return JSON')
        self.assertEqual(parse_facts('[]'), [])
        chat, _, job = self.turn('你好')
        self.h.apply_memory(job, [])
        self.assertEqual(self.h.memory_jobs(), [])
        self.h.delete(chat)
        self.assertFalse(self.h.apply_memory(job, [self.fact('迟到结果')]))
