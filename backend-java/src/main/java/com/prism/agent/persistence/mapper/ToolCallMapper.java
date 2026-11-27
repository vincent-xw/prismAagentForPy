package com.prism.agent.persistence.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.prism.agent.persistence.entity.ToolCallEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface ToolCallMapper extends BaseMapper<ToolCallEntity> {

    @Select("SELECT * FROM tool_calls WHERE id = #{callId} FOR UPDATE")
    ToolCallEntity lockById(@Param("callId") String callId);
}
