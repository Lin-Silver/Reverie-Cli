# 北堤开启任务

## 仪器供电

测潮仪位于西侧测潮棚，初始供电状态为false。
必须从仓库取得铜线，再在棚内保险盒装入铜线，才能使instrument.powered为true。
绿绳和装饰线缆不能替代铜线；它们没有任务物品的resource_id。

## 读取与发信

仪器通电后才能读取record.17。
有效记录给出water_limit_time=04:05，旁边的tourist_plaque写04:20并明确标为游客示意。
玩家阅读游客牌不能设置record.confirmed。
确认记录后，灯台才能进入emergency_signal交互。
紧急信号要求红灯连续三闪；白灯常亮只表示航道开放。

## 门与交付

北堤守门人只在instrument.powered、record.confirmed和signal.accepted都为true时开门。
钥匙warehouse.key只开仓库，不在north_gate所需条件中。
通过北堤后，玩家把档案交给school.archivist，设置archive.delivered。
只有north_gate.open和archive.delivered同时为true，结局界面才可出现。

## 失败和恢复

错误灯号保留任务进度，消耗一次尝试，并显示正确规则的文字提示。
落入浅水会回到最近安全点，不清空已经确认的记录或已开启的门。
取消交付对话不设置archive.delivered，下次仍可继续。
