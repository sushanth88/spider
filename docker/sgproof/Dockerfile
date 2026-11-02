FROM raghav0401/sgproof-scraper:latest

WORKDIR /app

COPY database.py /app/shared_database.py
COPY sgproof_database_adapter.py /app/database.py

CMD ["python", "run_scraper.py"]