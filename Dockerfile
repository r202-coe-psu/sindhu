FROM debian:sid
RUN echo 'deb http://mirrors.psu.ac.th/debian/ sid main contrib non-free' > /etc/apt/sources.list
# RUN echo 'deb http://mirror.kku.ac.th/debian/ sid main contrib non-free' >> /etc/apt/sources.list
RUN apt update && apt upgrade -y
RUN apt install -y python3.13 python3.13-dev python3.13-venv python3-pip npm locales \
    build-essential cmake libopenblas-dev gfortran cargo \
    && apt-get autoremove -y \
    && apt-get autoclean \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN sed -i '/th_TH.UTF-8/s/^# //g' /etc/locale.gen && locale-gen

RUN python3.13 -m venv /venv
ENV PYTHON=/venv/bin/python3.13

RUN $PYTHON -m pip install wheel poetry gunicorn 

WORKDIR /app/clients/sindhu-client
ADD clients/sindhu-client /app/clients/sindhu-client

RUN . /venv/bin/activate \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --only main

WORKDIR /app
COPY sindhu/cmd /app/sindhu/cmd
COPY poetry.lock pyproject.toml README.md /app/
RUN . /venv/bin/activate \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --only main \	
    && mkdir -p sindhu/web/static/brython_modules/ \
    && poetry run brython-cli update --update-dir sindhu/web/static/brython_modules/

WORKDIR /app/sindhu/web/static
COPY sindhu/web/static/package.json sindhu/web/static/package-lock.json ./
RUN npm install
COPY sindhu/web/static/ ./
RUN npm run tw:minify

WORKDIR /app
COPY . /app

RUN cd /app/sindhu/web/static/brython; \
    for i in $(ls -d */); \
    do \
    cd $i; \
    $PYTHON -m brython make_package ${i%%/}; \
    mv *.brython.js ..; \
    cd ..; \
    done

RUN npm run tw:minify --prefix sindhu/web/static
