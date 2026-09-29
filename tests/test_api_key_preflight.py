import subprocess
from types import SimpleNamespace
import pytest
from scripts.api_key_preflight import main


@pytest.mark.parametrize('result,expected',[(0,'API_KEY_ACCESSIBLE'),(1,'API_KEY_UNAVAILABLE'),('timeout','API_KEY_ACCESS_TIMED_OUT')])
def test_preflight_never_prints_credential_or_subprocess_details(monkeypatch,capsys,result,expected):
    def run(*args,**kwargs):
        if result=='timeout': raise subprocess.TimeoutExpired('PRIVATE_COMMAND',10)
        return SimpleNamespace(returncode=result,stdout=b'PRIVATE_KEY',stderr=b'PRIVATE_DETAIL')
    monkeypatch.setattr(subprocess,'run',run)
    assert main()==(0 if result==0 else 2)
    output=capsys.readouterr().out
    assert expected in output
    assert 'PRIVATE' not in output
