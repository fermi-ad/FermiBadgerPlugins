# FermiBadgerPlugins - Use Badger to run Xopt at Fermilab
Use this repo is one of two ways:

## 1. Install and run by hand:
```bash
conda create -n badger-env python=3.12.1 badger-opt==1.4.2
conda activate badger-env 
pip install "acsys[settings]"==0.12.8 --extra-index-url https://www-bd.fnal.gov/pip3 --no-cache-dir
git clone git@github.com:fermi-ad/FermiBadgerPlugins.git
cd FermiBadgerPlugins
badger -g -cf config.yaml
```

## 2. or Build a container image for running with Docker or podman
 - To build: 
```bash
    cd root-of-this-repo/
    docker build -t <image-name> .
```

- To run 
```bash
    docker run --rm <image-name>
```
- To run your script directly without rebuilding the image:
```bash
    docker run --rm -v .:/app <image-name> <your-script>
```
