import uvicorn
import logging
from speech_xray.product.config import load_settings

if __name__ == '__main__':
    settings = load_settings()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
    uvicorn.run('speech_xray.api.app:app', host=settings.host, port=settings.port, workers=1)
