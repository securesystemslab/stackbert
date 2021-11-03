#!/usr/bin/env bash

fairseq-preprocess \
    --only-source \
    --trainpref data-src/pretrain-32bit-ideal/train.in \
    --validpref data-src/pretrain-32bit-ideal/valid.in \
    --destdir data-bin/pretrain-32bit-ideal \
    --workers 40
