ARG MAGEAI_VERSION
ARG PROJECT_NAME
ARG USER_CODE_PATH=/home/src/${PROJECT_NAME:-sindhu}
ARG DEBIAN_FRONTEND=noninteractive

FROM mageai/mageai:${MAGEAI_VERSION:-latest}
RUN echo 'deb http://mirrors.psu.ac.th/debian/ bookworm main contrib non-free' > /etc/apt/sources.list

# RUN apt purge -y  -f unixodbc-common libodbc2

RUN apt update -y && apt -y install apt-utils && ACCEPT_EULA=Y apt upgrade -y -q
RUN apt -y install locales apt-utils \
    && apt-get autoremove -y \
    && apt-get autoclean \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN sed -i '/th_TH.UTF-8/s/^# //g' /etc/locale.gen && locale-gen


# Add non-root user for Mage service
RUN adduser --disabled-password --gecos '' mage && adduser mage mage

# Grant the user permissions to the Mage related directories
RUN mkdir /home/src/mage_data; chown -R mage /home/src/mage_data
RUN mkdir /home/src/default_repo; chown -R mage /home/src/default_repo

# Install custom Python libraries
COPY requirements.txt ${USER_CODE_PATH}/requirements.txt
RUN pip3 install -r ${USER_CODE_PATH}/requirements.txt
# Install custom libraries within 3rd party libraries (e.g. dbt packages)
# RUN python3 /app/install_other_dependencies.py --path ${USER_CODE_PATH}

# Set the Mage user
USER mage

# ENV PYTHONPATH="${PYTHONPATH}"
ENV PYTHONPATH="${PYTHONPATH}:/home/mage_code"

WORKDIR /home/src
CMD ["/bin/sh", "-c", "/app/run_app.sh"]
