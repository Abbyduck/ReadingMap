# Reading Map 协作约束

在修改审核工作台、Research、Catalog 写入或推荐系统前，先阅读 [docs/review-workflow-contract.md](docs/review-workflow-contract.md)。

该文档记录用户已经确认、不得顺手改变的行为。若任务必须改变其中任何一条，动手前明确告诉用户将触及哪条约束、为什么、会产生什么影响，并取得用户确认。修复实现错误时也要先保证这些行为不回退。修改后运行相关回归测试，并在交付时说明验证结果。
