"""Set DNS only inside the dedicated build distro."""
from pathlib import Path
import configparser

config = configparser.ConfigParser()
path = Path('/etc/wsl.conf')
config.read(path)
if not config.has_section('network'):
    config.add_section('network')
config.set('network', 'generateResolvConf', 'false')
with path.open('w') as output:
    config.write(output)
resolver = Path('/etc/resolv.conf')
if resolver.is_symlink():
    resolver.unlink()
resolver.write_text('nameserver 192.168.31.1\nnameserver 223.5.5.5\noptions timeout:3 attempts:2\n')
