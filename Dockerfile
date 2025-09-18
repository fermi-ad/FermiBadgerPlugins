FROM continuumio/miniconda3
# Will copy from existing Docker image
COPY --from=continuumio/miniconda3:4.12.0 /opt/conda /opt/conda
ENV PATH=/opt/conda/bin:$PATH

# Configure channels
RUN conda config --add channels conda-forge
RUN conda config --remove channels defaults

WORKDIR /usr/src/app
COPY environment.yml .
# Create the conda env with badger as specified in the YAML file, and initialize the env:
RUN conda env create -n badger-envX --file environment.yml
SHELL ["conda", "init", "bash"]

##SHELL ["conda", "run", "-n", "badger-envX", "install", "mamba"]
#RUN conda activate badger-envX
#RUN conda install mamba

# Make RUN commands use the new environment:
##SHELL ["mamba", "run", "-n", "badger-envX", "install", "badger-opt=1.4.3"]
SHELL ["conda", "run", "-n", "badger-envX", "/bin/bash", "-c"]

### Demonstrate the environment is activated:
RUN echo "Make sure badger is installed:"
RUN python -c "import badger"

### Fix the missing libGL.so.1 issue
RUN apt-get update
RUN apt install -y libgl1-mesa-glx

### Automatically activate badger-envX
RUN echo "source activate badger-envX" > ~/.bashrc
ENV PATH /opt/conda/envs/badger-envX/bin:$PATH

# Badger playground, should contain all plugins/data
WORKDIR /playground

# The code to run when container is started:
ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "badger-envX", "badger"]