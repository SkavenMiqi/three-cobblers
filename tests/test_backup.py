import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from talkapp.storage import History
from talkapp.backup import archive, encrypt, decrypt, restore, BackupConfig
from talkapp.client import messages_for_api, image_list


class BackupTests(unittest.TestCase):
    def test_encrypted_roundtrip_excludes_temporary_and_rejects_wrong_password(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            h = History(root / 'history.db')
            chat = h.create()
            h.append(chat, 'user', '要保留的消息')
            temporary = h.create(temporary=True)
            h.append(temporary, 'user', '临时消息')
            payload = encrypt(archive(root), 'test-password')
            self.assertNotIn('要保留'.encode(), payload)
            with self.assertRaises(ValueError):
                decrypt(payload, 'wrong-password')
            h.delete(chat)
            h.close()
            restore(payload, 'test-password', root)
            recovered = History(root / 'history.db')
            self.assertEqual(recovered.messages(chat)[0][1], '要保留的消息')
            self.assertFalse(recovered.path(temporary))
            recovered.close()

    def test_tampered_backup_rejected_without_mutation(self):
        value = bytearray(encrypt(b'test', 'test-password'))
        value[-1] ^= 1
        with self.assertRaises(ValueError):
            decrypt(bytes(value), 'test-password')

    def test_temporary_not_in_retrieval_and_crash_cleanup(self):
        h = History(':memory:')
        chat = h.create(temporary=True)
        h.append(chat, 'user', '不能进入记忆的临时内容')
        self.assertEqual(h.search(), [])
        self.assertEqual(h.digest_work(), ([], []))
        h.recover_interrupted()
        self.assertEqual(h.path(chat), [])
        h.close()

    def test_multiple_images_backward_compatible(self):
        import json
        first, second = 'data:image/jpeg;base64,AA==', 'data:image/jpeg;base64,BB=='
        self.assertEqual(image_list(first), [first])
        result = messages_for_api([('user', '对比', json.dumps([first, second]))], '')
        self.assertEqual(len(result[0]['content']), 3)

    def test_backup_config_needs_password_when_enabled(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'TALKAPP_DATA_DIR': folder}):
            with self.assertRaises(ValueError):
                BackupConfig(enabled=True).save()
            BackupConfig(enabled=True, passphrase='test-pass').save()
            self.assertTrue(BackupConfig.load().enabled)

    def test_webdav_upload_is_encrypted_and_rotated(self):
        import httpx
        from talkapp.backup import BackupService
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'TALKAPP_DATA_DIR': folder}):
            h = History()
            h.create()
            h.close()
            BackupConfig(enabled=True, passphrase='test-pass', webdav_url='https://example.com/backups', keep=1).save()
            uploaded = []
            def handler(request):
                uploaded.append(request.content)
                return httpx.Response(201)
            notices = []
            service = BackupService(notices.append)
            with patch('talkapp.backup.httpx.Client', return_value=httpx.Client(transport=httpx.MockTransport(handler))):
                service.run(force=True)
                self.assertTrue(service.lock.acquire(timeout=10))
                service.lock.release()
            self.assertEqual(len(uploaded), 1)
            self.assertTrue(uploaded[0].startswith(b'TALKBACK1'))
            self.assertEqual(len(list((Path(folder) / 'backups').glob('*.talkbackup'))), 1)
