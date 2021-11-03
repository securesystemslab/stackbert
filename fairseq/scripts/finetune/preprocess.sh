#!/usr/bin/env bash

for i in 0 1 2 3 
do
    rm -rf data-bin/finetune-32bitideal-O$i
    mkdir data-bin/finetune-32bitideal-O$i
    mkdir data-bin/finetune-32bitideal-O$i/input0
    mkdir data-bin/finetune-32bitideal-O$i/label

    fairseq-preprocess \
        --only-source \
        --srcdict data-bin/pretrain-32bit-ideal/dict.txt \
        --trainpref data-src/finetune-32bitideal-O$i/train.data \
        --validpref data-src/finetune-32bitideal-O$i/valid.data \
        --destdir data-bin/finetune-32bitideal-O$i/input0 \
        --workers 40

    fairseq-preprocess \
        --only-source \
        --trainpref data-src/finetune-32bitideal-O$i/train.label \
        --validpref data-src/finetune-32bitideal-O$i/valid.label \
        --destdir data-bin/finetune-32bitideal-O$i/label \
        --workers 40
done
