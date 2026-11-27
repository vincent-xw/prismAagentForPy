package com.prism.agent.persistence.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.prism.agent.persistence.entity.RunEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface RunMapper extends BaseMapper<RunEntity> {

    /** 行锁 + SKIP LOCKED：多 Worker 并发 claim 时不会抢到同一行。必须在事务内调用。 */
    @Select("SELECT * FROM runs WHERE status = 'queued' ORDER BY created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED")
    RunEntity lockNextQueued();

    @Update("UPDATE runs SET last_event_seq = last_event_seq + 1 WHERE id = #{runId}")
    int incrementEventSeq(@Param("runId") String runId);

    @Select("SELECT last_event_seq FROM runs WHERE id = #{runId}")
    Integer currentEventSeq(@Param("runId") String runId);

    @Update("UPDATE runs SET last_event_seq = GREATEST(last_event_seq, #{seq}) WHERE id = #{runId}")
    int raiseEventSeq(@Param("runId") String runId, @Param("seq") int seq);
}
