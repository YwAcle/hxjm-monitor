package edu.cqupt.hxjm.algdeployment.mapper;

import edu.cqupt.hxjm.algdeployment.domain.MediaAsset;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface MediaAssetMapper {
    int insertMediaAsset(MediaAsset mediaAsset);

    List<MediaAsset> selectLatestMediaAssets();
}
