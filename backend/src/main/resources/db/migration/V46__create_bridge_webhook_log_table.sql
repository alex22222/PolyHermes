create table bridge_webhook_log (
  id bigint primary key auto_increment,
  bridge_id varchar(100) not null comment 'Bridge 标识',
  event varchar(50) not null comment '事件类型，如 leader_trade',
  leader_address varchar(100) comment 'Leader 钱包地址',
  leader_name varchar(200) comment 'Leader 名称',
  transaction_hash varchar(100) comment '原始交易哈希',
  condition_id varchar(100) comment '市场 condition id',
  market_slug varchar(200) comment '市场 slug',
  side varchar(20) comment '交易方向 BUY/SELL',
  outcome varchar(100) comment '投注结果',
  request_body text comment '请求体 JSON',
  response_body text comment '响应体',
  status_code int comment 'HTTP 状态码',
  status varchar(30) not null comment 'SUCCESS/FAILED/SKIPPED',
  error_message text comment '错误信息',
  created_at bigint not null,
  updated_at bigint not null
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci comment='Bridge webhook 调用日志';

create index idx_bridge_webhook_log_created_at on bridge_webhook_log(created_at desc);
create index idx_bridge_webhook_log_status on bridge_webhook_log(status);
create index idx_bridge_webhook_log_tx_hash on bridge_webhook_log(transaction_hash);
