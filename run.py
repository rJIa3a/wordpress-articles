import os
import uvicorn
if __name__=='__main__':
 uvicorn.run('interlinker.app:app',host=os.getenv('APP_HOST','127.0.0.1'),port=int(os.getenv('APP_PORT','8000')),proxy_headers=True,forwarded_allow_ips=os.getenv('TRUSTED_PROXY_IPS','127.0.0.1'))
