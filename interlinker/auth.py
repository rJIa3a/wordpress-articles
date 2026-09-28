"""Local-first email/password auth with server-side, revocable sessions."""
import hashlib
import os
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import quote

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

from . import storage as db

PASSWORDS=PasswordHasher(time_cost=2,memory_cost=19456,parallelism=1)
SESSION_SECONDS=60*60*24*14
VERIFY_HOURS=24

def _now():return datetime.now(timezone.utc)
def _iso(value):return value.isoformat(timespec='seconds')
def _digest(value):return hashlib.sha256(value.encode()).hexdigest()
def _production():return os.getenv('APP_ENV','development').lower()=='production'
def verification_required():
 return _production() or os.getenv('EMAIL_VERIFICATION_REQUIRED','false').lower()=='true'
def _cookie_name():return '__Host-ui_session' if _production() else 'ui_session'
def cookie_name():return _cookie_name()

def rate_allowed(bucket,limit,window_seconds):
 now=int(_now().timestamp());key=_digest('rate:'+bucket)
 with db.connect() as c:
  row=c.execute('SELECT window_start,attempts FROM auth_rate_limits WHERE bucket_hash=?',(key,)).fetchone()
  if not row or now-row['window_start']>=window_seconds:
   c.execute('INSERT INTO auth_rate_limits(bucket_hash,window_start,attempts) VALUES(?,?,1) ON CONFLICT(bucket_hash) DO UPDATE SET window_start=excluded.window_start,attempts=1',(key,now));return True
  if row['attempts']>=limit:return False
  c.execute('UPDATE auth_rate_limits SET attempts=attempts+1 WHERE bucket_hash=?',(key,));return True

def clear_rate_limit(bucket):
 with db.connect() as c:c.execute('DELETE FROM auth_rate_limits WHERE bucket_hash=?',(_digest('rate:'+bucket),))

def validate_email(email):
 email=email.strip().lower()
 if len(email)>254 or email.count('@')!=1:return None
 local,domain=email.rsplit('@',1)
 if not local or not domain or '.' not in domain or any(ch.isspace() for ch in email):return None
 return email

def create_account(email,password,base_url):
 email=validate_email(email)
 if not email:raise ValueError('Введите корректный email')
 if len(password)<12:raise ValueError('Пароль должен содержать не менее 12 символов')
 if len(password.encode())>1024:raise ValueError('Пароль слишком длинный')
 if verification_required() and _production() and not os.getenv('SMTP_HOST'):raise RuntimeError('Для регистрации на сервере сначала настройте SMTP-почту')
 if not verification_required():
  try:
   with db.connect() as c:c.execute('INSERT INTO users(email,password_hash,email_verified) VALUES(?,?,1)',(email,PASSWORDS.hash(password)))
  except Exception as e:
   if 'UNIQUE constraint failed: users.email' in str(e):return {'created':False,'verification_required':False,'verification_url':None}
   raise
  return {'created':True,'verification_required':False,'verification_url':None}
 token=secrets.token_urlsafe(32);expires=_iso(_now()+timedelta(hours=VERIFY_HOURS))
 try:
  with db.connect() as c:
   c.execute('INSERT INTO users(email,password_hash) VALUES(?,?)',(email,PASSWORDS.hash(password)))
   user_id=c.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()[0]
   c.execute('INSERT INTO email_tokens(user_id,token_hash,expires) VALUES(?,?,?)',(user_id,_digest(token),expires))
 except Exception as e:
  if 'UNIQUE constraint failed: users.email' in str(e):return {'created':False,'verification_url':None}
  raise
 url=f'{base_url.rstrip("/")}/?verify={quote(token)}'
 if os.getenv('SMTP_HOST'):_send_verification(email,url)
 elif _production():raise RuntimeError('Не настроена отправка почты')
 return {'created':True,'verification_required':True,'verification_url':url if not _production() else None}

def resend_verification(email,base_url):
 email=validate_email(email or '')
 if not email:return None
 with db.connect() as c:
  row=c.execute('SELECT id,email_verified FROM users WHERE email=?',(email,)).fetchone()
  if not row or row['email_verified']:return None
  token=secrets.token_urlsafe(32);expires=_iso(_now()+timedelta(hours=VERIFY_HOURS))
  c.execute('UPDATE email_tokens SET used=1 WHERE user_id=? AND used=0',(row['id'],))
  c.execute('INSERT INTO email_tokens(user_id,token_hash,expires) VALUES(?,?,?)',(row['id'],_digest(token),expires))
 url=f'{base_url.rstrip("/")}/?verify={quote(token)}'
 if os.getenv('SMTP_HOST'):_send_verification(email,url)
 elif _production():raise RuntimeError('Не настроена отправка почты')
 return {'verification_url':url if not _production() else None}

def _send_verification(email,url):
 msg=EmailMessage();msg['Subject']='Подтвердите адрес Universal Interlinker';msg['From']=os.getenv('SMTP_FROM',os.getenv('SMTP_USER',''));msg['To']=email
 msg.set_content('Откройте ссылку, чтобы подтвердить email и активировать аккаунт:\n\n'+url+'\n\nСсылка действует 24 часа. Если вы не создавали аккаунт, проигнорируйте письмо.')
 host=os.environ['SMTP_HOST'];port=int(os.getenv('SMTP_PORT','587'))
 if os.getenv('SMTP_SSL','').lower()=='true':
  with smtplib.SMTP_SSL(host,port,context=ssl.create_default_context(),timeout=20) as server:
   if os.getenv('SMTP_USER'):server.login(os.environ['SMTP_USER'],os.environ.get('SMTP_PASSWORD',''))
   server.send_message(msg)
 else:
  with smtplib.SMTP(host,port,timeout=20) as server:
   server.ehlo()
   if os.getenv('SMTP_STARTTLS','true').lower()=='true':
    server.starttls(context=ssl.create_default_context());server.ehlo()
   elif _production() or host.lower() not in ('mailpit','localhost','127.0.0.1','::1'):
    raise RuntimeError('Для внешнего SMTP требуется TLS или SMTPS')
   if os.getenv('SMTP_USER'):server.login(os.environ['SMTP_USER'],os.environ.get('SMTP_PASSWORD',''))
   server.send_message(msg)

def verify_email(token):
 if not token or len(token)>200:return False
 with db.connect() as c:
  updated=c.execute('UPDATE email_tokens SET used=1 WHERE token_hash=? AND used=0 AND expires>? RETURNING user_id',(_digest(token),_iso(_now()))).fetchone()
  if not updated:return False
  c.execute('UPDATE users SET email_verified=1 WHERE id=?',(updated['user_id'],))
 return True

def login(email,password):
 email=validate_email(email or '')
 matches=db.rows('SELECT * FROM users WHERE email=?',(email,)) if email else []
 row=matches[0] if matches else None
 valid=False
 if row:
  try:PASSWORDS.verify(row['password_hash'],password);valid=True
  except (VerifyMismatchError,VerificationError):pass
 if not row or not valid or (verification_required() and not row['email_verified']):raise ValueError('Неверный email, пароль или неподтверждённый адрес')
 token=secrets.token_urlsafe(32);expires=_iso(_now()+timedelta(seconds=SESSION_SECONDS))
 with db.connect() as c:c.execute('INSERT INTO sessions(user_id,token_hash,expires) VALUES(?,?,?)',(row['id'],_digest(token),expires))
 return token,{'id':row['id'],'email':row['email']}

def session_user(token):
 if not token or len(token)>200:return None
 verification_filter=' AND u.email_verified=1' if verification_required() else ''
 rows=db.rows('SELECT u.id,u.email FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.revoked=0 AND s.expires>?'+verification_filter,(_digest(token),_iso(_now())))
 return rows[0] if rows else None

def logout(token):
 if token:
  with db.connect() as c:c.execute('UPDATE sessions SET revoked=1 WHERE token_hash=?',(_digest(token),))
