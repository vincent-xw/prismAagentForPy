package com.prism.agent.persistence.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.prism.agent.persistence.entity.RunEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface RunMapper extends BaseMapper<RunEntity> {

    /** 行锁 + SKIP LOCKED：多 Worker 并发 claim 时不会抢到同一行。必须在事务内调用。 */
    @Select("SELECT * FROM runs WHERE status = 'queued' ORDER BY created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED")
    RunEntity lockNextQueued();
}
