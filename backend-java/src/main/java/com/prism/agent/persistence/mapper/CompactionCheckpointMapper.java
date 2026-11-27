package com.prism.agent.persistence.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.prism.agent.persistence.entity.CompactionCheckpointEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CompactionCheckpointMapper extends BaseMapper<CompactionCheckpointEntity> {
}
