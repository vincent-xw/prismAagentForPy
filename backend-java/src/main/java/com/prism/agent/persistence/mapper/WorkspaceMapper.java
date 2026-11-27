package com.prism.agent.persistence.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.prism.agent.persistence.entity.WorkspaceEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface WorkspaceMapper extends BaseMapper<WorkspaceEntity> {
}
