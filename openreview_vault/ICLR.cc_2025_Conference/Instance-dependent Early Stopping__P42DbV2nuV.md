---
title: Instance-dependent Early Stopping
aliases: []
time_start: '202409'
time_end: '202501'
AcceptBy: ICLR 2025
tags:
- early-stopping
- supervised-learning
- deep-learning
- efficiency
- sample-selection
- data-pruning
url(Official): ''
url(arXiv): https://arxiv.org/abs/2502.07547
url(Github): ''
url(OR): https://openreview.net/forum?id=P42DbV2nuV
url(Others):
- https://openreview.net/pdf/8fddee1917f5289fe7908965f534e27f36e3f4db.pdf
- https://www.semanticscholar.org/paper/d643ca410b005032b7b398569d7f8ddfa616ba76
Baselines:
- Random Remove
- Small Loss & Rescale
- Conventional Early Stopping
- SB
- DIHCL
- EfficientTrain
- InfoBatch
- No Removal
Benchmarks:
- CIFAR-10
- CIFAR-100
- ImageNet-1k
- Caltech-101
- PASCAL VOC 2007
- PASCAL VOC 2012
- CelebA
Metrics:
- Test accuracy
- Mini-batch Saved
- Wall-time Speedup
- mAP
- mIoU
- Training loss
- Gradient norm
- SAM value
- Maximum eigenvalue of the Hessian matrix
- Recall
- Demographic Parity Difference
- Max Eigenvalue of Hessian
- DPD
CitedBy:
- 1@2024.10.01
- 1@2025.01.01
- 3@2025.04.01
- 5@2025.07.01
- 7@2025.10.01
- 8@2026.01.01
- 11@2026.04.01
- 14@2026.06.06
Authors:
- Suqin Yuan
- Runqi Lin
- Lei Feng
- Bo Han
- Tongliang Liu
1stAuthorHP: https://suqinyuan.github.io
Affiliations:
- The University of Sydney
- University of Sydney
- Singapore University of Technology and Design
- MBZUAI
- Mohamed bin Zayed University of Artificial Intelligence
Creator: agent4research-openreview
EditLogs:
- 2026.06.06创建
forum_id: P42DbV2nuV
number: 2
presentation_type: Spotlight
primary_area: unsupervised, self-supervised, semi-supervised, and supervised representation learning
keywords:
- Early Stopping
- Supervised Learning
- Deep Learning
- Efficiency
- Sample Selection
- Data Pruning
authorids:
- ~Suqin_Yuan1
- ~Runqi_Lin1
- ~Lei_Feng1
- ~Bo_Han1
- ~Tongliang_Liu1
arxiv_id: '2502.07547'
doi: 10.48550/arXiv.2502.07547
corpus_id: '276258809'
s2_paper_id: d643ca410b005032b7b398569d7f8ddfa616ba76
openreview_pdf: https://openreview.net/pdf/8fddee1917f5289fe7908965f534e27f36e3f4db.pdf
auto_extracted:
- Baselines
- Benchmarks
- Metrics
---

# Instance-dependent Early Stopping

> [!tldr] TL;DR
> We propose an instance-dependent early stopping method that stops training at the instance level by determining whether the model has fully learned an instance. It reduces computational costs while maintaining or even improving model performance.

**Authors:** Suqin Yuan, Runqi Lin, Lei Feng, Bo Han, Tongliang Liu

## Abstract

In machine learning practice, early stopping has been widely used to regularize models and can save computational costs by halting the training process when the model's performance on a validation set stops improving. However, conventional early stopping applies the same stopping criterion to all instances without considering their individual learning statuses, which leads to redundant computations on instances that are already well-learned. To further improve the efficiency, we propose an Instance-dependent Early Stopping (IES) method that adapts the early stopping mechanism from the entire training set to the instance level, based on the core principle that once the model has mastered an instance, the training on it should stop. IES considers an instance as mastered if the second-order differences of its loss value remain within a small range around zero. This offers a more consistent measure of an instance's learning status compared with directly using the loss value, and thus allows for a unified threshold to determine when an instance can be excluded from further backpropagation. We show that excluding mastered instances from backpropagation can increase the gradient norms, thereby accelerating the decrease of the training loss and speeding up the training process. Extensive experiments on benchmarks demonstrate that IES method can reduce backpropagation instances by 10%-50% while maintaining or even slightly improving the test accuracy and transfer learning performance of a model.

## Notes

<!-- your notes here; this section is preserved on re-scrape -->
