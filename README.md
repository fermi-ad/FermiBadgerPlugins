# XoptBadger - can we make it work? We can!
From a clean conda environment:

```bash
conda create -n xopt-dev python=3.12.1 xopt
conda activate xopt-dev
conda install badger-opt
pip install "acsys[settings]"==0.12.8 --extra-index-url https://www-bd.fnal.gov/pip3 --no-cache-dir
pip install requests
badger -g
```
python --version


