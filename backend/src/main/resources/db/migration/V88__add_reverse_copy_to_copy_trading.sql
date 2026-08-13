ALTER TABLE copy_trading
  ADD COLUMN reverse_copy BOOLEAN NOT NULL DEFAULT FALSE COMMENT '二元市场反向 outcome 跟单';
