"""One-shot, secret-free verification of the operator's OpenAI Keychain item."""
import json
import subprocess


def main():
    try:
        result=subprocess.run(['/usr/bin/security','find-generic-password','-s',
            'robinhood-shadow-openai','-a','rehearsal','-w'],capture_output=True,timeout=10)
        ok=result.returncode==0 and bool(result.stdout.strip())
        status='API_KEY_ACCESSIBLE' if ok else 'API_KEY_UNAVAILABLE'
        del result
    except subprocess.TimeoutExpired:
        ok=False
        status='API_KEY_ACCESS_TIMED_OUT'
    print(json.dumps({'status':status,'secret_disclosed':False}),flush=True)
    return 0 if ok else 2


if __name__=='__main__':
    raise SystemExit(main())
