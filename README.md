# FermiBadgerPlugins - Use Badger to run Xopt at Fermilab
Use this repo is one of two ways:

## 1. Install and run by hand:
```bash
git clone git@github.com:fermi-ad/FermiBadgerPlugins.git
cd FermiBadgerPlugins
conda create -n badger-env python=3.12.1 badger-opt=1.4.3
conda activate badger-env 
pip install "acsys[settings]"==0.12.8 --extra-index-url https://www-bd.fnal.gov/pip3 --no-cache-dir
badger -g -cf config.yaml
```
*Nota Bene* ```pip install``` will fail if executed from outside of the FNAL private network (VPN works).

## 2. or Build a container image for running with Docker or podman
 - To build: (may require changes to your Docker descktop for sufficient RAM or other memory resources)
```bash
    cd root-of-this-repo/
    docker build -t adregistry.fnal.gov/ml-autotune/testimage:latest --platform linux/amd64 .
    docker login -u $USER adregistry.fnal.gov
    ## Services password ##
    docker push  adregistry.fnal.gov/ml-autotune/testimage:latest  
```

- To run 
```bash
    docker run --rm docker run --rm -v .:/app testimage:latest 
```
- To run your script directly without rebuilding the image:
```bash
   docker run --rm -v .:/app testimage:latest 
```
