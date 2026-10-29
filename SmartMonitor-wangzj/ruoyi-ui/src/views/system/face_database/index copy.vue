<template>
  <div class="app-container">
    <el-form :model="queryParams"
             ref="queryForm"
             size="small"
             :inline="true"
             v-show="showSearch"
             label-width="68px">
      <el-form-item label="人员姓名"
                    prop="userName">
        <el-input v-model="queryParams.userName"
                  placeholder="请输入人员姓名"
                  clearable
                  @keyup.enter.native="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary"
                   icon="el-icon-search"
                   size="mini"
                   @click="handleQuery">搜索</el-button>
        <el-button icon="el-icon-refresh"
                   size="mini"
                   @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10"
            class="mb8">
      <el-col :span="1.5">
        <el-button type="primary"
                   plain
                   icon="el-icon-plus"
                   size="mini"
                   @click="handleAdd"
                   v-hasPermi="['system:face_database:add']">新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="success"
                   plain
                   icon="el-icon-edit"
                   size="mini"
                   :disabled="single"
                   @click="handleUpdate"
                   v-hasPermi="['system:face_database:edit']">修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="danger"
                   plain
                   icon="el-icon-delete"
                   size="mini"
                   :disabled="multiple"
                   @click="handleDelete"
                   v-hasPermi="['system:face_database:remove']">删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="warning"
                   plain
                   icon="el-icon-download"
                   size="mini"
                   @click="handleExport"
                   v-hasPermi="['system:face_database:export']">导出</el-button>
      </el-col>
      <right-toolbar :showSearch.sync="showSearch"
                     @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading"
              :data="face_databaseList"
              @selection-change="handleSelectionChange">
      <el-table-column type="selection"
                       width="55"
                       align="center" />
      <el-table-column label="ID"
                       align="center"
                       prop="id" />
      <el-table-column label="人脸ID"
                       align="center"
                       prop="faceId" />
      <el-table-column label="人员姓名"
                       align="center"
                       prop="userName" />
      <el-table-column label="性别"
                       align="center"
                       prop="gender">
        <template slot-scope="scope">
          <span>{{ scope.row.gender === 1 ? '男' : '女' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="年龄"
                       align="center"
                       prop="age" />
      <el-table-column label="质量"
                       align="center"
                       prop="quality" />
      <el-table-column label="人脸特征向量"
                       align="center"
                       prop="faceEncoding"
                       show-overflow-tooltip>
        <template slot-scope="scope">
          <span class="feature-text">{{ scope.row.faceEncoding }}</span>
        </template>
      </el-table-column>
      <el-table-column label="人脸原始图像"
                       align="center"
                       prop="faceImage"
                       width="100">
        <template slot-scope="scope">
          <image-preview :src="getImageUrl(scope.row.faceImage)"
                         :width="50"
                         :height="50" />
        </template>
      </el-table-column>
      <el-table-column label="人脸缩略图"
                       align="center"
                       prop="faceImageThumbnail" />
      <el-table-column label="元数据"
                       align="center"
                       prop="metadata" />
      <el-table-column label="状态"
                       align="center"
                       prop="status">
        <template slot-scope="scope">
          <el-switch v-model="scope.row.status"
                     :active-value="1"
                     :inactive-value="0"
                     @change="handleStatusChange(scope.row)">
          </el-switch>
        </template>
      </el-table-column>
      <el-table-column label="创建时间"
                       align="center"
                       prop="createTime"
                       width="180">
        <template slot-scope="scope">
          <span>{{ parseTime(scope.row.createTime, '{y}-{m}-{d} {h}:{i}:{s}') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="更新时间"
                       align="center"
                       prop="updateTime"
                       width="180">
        <template slot-scope="scope">
          <span>{{ parseTime(scope.row.updateTime, '{y}-{m}-{d} {h}:{i}:{s}') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作"
                       align="center"
                       class-name="small-padding fixed-width">
        <template slot-scope="scope">
          <el-button size="mini"
                     type="text"
                     icon="el-icon-edit"
                     @click="handleUpdate(scope.row)"
                     v-hasPermi="['system:face_database:edit']">修改</el-button>
          <el-button size="mini"
                     type="text"
                     icon="el-icon-delete"
                     @click="handleDelete(scope.row)"
                     v-hasPermi="['system:face_database:remove']">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total>0"
                :total="total"
                :page.sync="queryParams.pageNum"
                :limit.sync="queryParams.pageSize"
                @pagination="getList" />

    <!-- 添加或修改人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等对话框 -->
    <el-dialog :title="title"
               :visible.sync="open"
               width="500px"
               append-to-body>
      <el-form ref="form"
               :model="form"
               :rules="rules"
               label-width="80px">
        <el-form-item label="人脸ID">
          <el-input v-model="form.faceId"
                    disabled
                    placeholder="系统自动生成" />
        </el-form-item>
        <el-form-item label="人员姓名"
                      prop="userName">
          <el-input v-model="form.userName"
                    placeholder="请输入人员姓名" />
        </el-form-item>
        <el-form-item label="性别"
                      prop="gender">
          <el-radio-group v-model="form.gender">
            <el-radio :label="1">男</el-radio>
            <el-radio :label="2">女</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="年龄"
                      prop="age">
          <el-input-number v-model="form.age"
                           :min="0"
                           :max="150"
                           placeholder="请输入年龄" />
        </el-form-item>
        <el-form-item label="质量"
                      prop="quality">
          <el-input-number v-model="form.quality"
                           :min="0"
                           :max="1"
                           :precision="2"
                           :step="0.01"
                           placeholder="请输入质量值" />
        </el-form-item>
        <el-form-item label="人脸原始图像"
                      prop="faceImage">
          <image-upload v-model="form.faceImage" />
        </el-form-item>
        <el-form-item label="人脸特征"
                      prop="faceEncoding">
          <el-input v-model="form.faceEncoding"
                    type="textarea"
                    :rows="4"
                    placeholder="请输入人脸特征向量" />
        </el-form-item>
        <el-form-item label="元数据">
          <editor v-model="form.metadata"
                  :min-height="192" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio :label="1">启用</el-radio>
            <el-radio :label="0">作废</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <div slot="footer"
           class="dialog-footer">
        <el-button type="primary"
                   @click="submitForm">确 定</el-button>
        <el-button @click="cancel">取 消</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { listFace_database, getFace_database, delFace_database, addFace_database, updateFace_database, getFace_database_all, addFace, updateFace } from "@/api/system/face_database";

export default {
  name: "Face_database",
  data () {
    return {
      // 遮罩层
      loading: true,
      // 选中数组
      ids: [],
      // 非单个禁用
      single: true,
      // 非多个禁用
      multiple: true,
      // 显示搜索条件
      showSearch: true,
      // 总条数
      total: 0,
      // 人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等表格数据
      face_databaseList: [],
      // 弹出层标题
      title: "",
      // 是否显示弹出层
      open: false,
      // 查询参数
      queryParams: {
        pageNum: 1,
        pageSize: 10,
        userName: null,
        status: null,
      },
      // 表单参数
      form: {},
      // 表单校验
      rules: {
        userName: [
          { required: true, message: "人员姓名不能为空", trigger: "blur" }
        ],
      },
    };
  },
  created () {
    this.getList();
  },
  methods: {
    /** 查询人脸信息，用于存储每个识别到的人脸的基本信息，包括特征向量、图像、元数据等列表 */
    getList () {
      this.loading = true;
      listFace_database(this.queryParams).then(response => {
        this.face_databaseList = response.rows;
        this.total = response.total;
        this.loading = false;
      });
    },
    // 取消按钮
    cancel () {
      this.open = false;
      this.reset();
    },
    // 表单重置
    reset () {
      this.form = {
        id: null,
        faceId: null,
        userName: null,
        gender: 1,  // 默认选择男性
        age: 0,
        quality: 0,
        faceEncoding: null,
        faceImage: null,
        faceImageThumbnail: null,
        metadata: null,
        status: 1,  // 默认为启用状态
      };
      this.resetForm("form");
    },
    /** 搜索按钮操作 */
    handleQuery () {
      this.queryParams.pageNum = 1;
      this.getList();
    },
    /** 重置按钮操作 */
    resetQuery () {
      this.resetForm("queryForm");
      this.handleQuery();
    },
    // 多选框选中数据
    handleSelectionChange (selection) {
      this.ids = selection.map(item => item.id)
      this.single = selection.length !== 1
      this.multiple = !selection.length
    },
    /** 新增按钮操作 */
    handleAdd () {
      this.reset();
      // 生成唯一的人脸ID
      this.form.faceId = this.generateUniqueId();
      this.open = true;
      this.title = "添加人脸信息";
    },
    /** 修改按钮操作 */
    handleUpdate (row) {
      this.reset();
      const id = row.id || this.ids
      getFace_database(id).then(response => {
        this.form = response.data;
        this.open = true;
        this.title = "修改人脸信息";
      });
    },
    /** 将图片地址转换为base64 */
    async imageToBase64 (imageUrl) {
      try {
        const response = await fetch(process.env.VUE_APP_BASE_API + imageUrl);
        const blob = await response.blob();
        return new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result.split(',')[1]);
          reader.onerror = reject;
          reader.readAsDataURL(blob);
        });
      } catch (error) {
        console.error('图片转换失败:', error);
        return null;
      }
    },
    /** 提交按钮 */
    async submitForm () {
      this.$refs["form"].validate(async valid => {
        if (valid) {
          var face_Image_arr = [];
          // 将当前表单的图片地址转为base64并加入集合
          if (this.form.faceImage) {
            const imageUrls = this.form.faceImage.split(',');
            for (const url of imageUrls) {
              const base64Data = await this.imageToBase64(url);
              if (base64Data) {
                face_Image_arr.push(base64Data);
              }
            }
          }
          if (this.form.id != null) {
            var params = {
              images: face_Image_arr
            }
            var updateFaceRes;
            try {
              updateFaceRes = await updateFace(params);
            } catch (error) {
              console.error('调用算法服务失败:', error);
              this.$modal.msgError("调用算法服务失败，请重试");
            }
            console.log(updateFaceRes);
            if (updateFaceRes.code === 200) {
              if (!updateFaceRes.data.success) {
                this.$modal.msgError("人脸添加失败：" + updateFaceRes.data.message);
                return;
              }
              this.form.faceEncoding = JSON.stringify(updateFaceRes.data.embeddings).replace(/\s+/g, '');
              await updateFace_database(this.form).then(response => {
                this.$modal.msgSuccess("修改成功");
                this.open = false;
                this.getList();
              });
            } else {
              this.$modal.msgError("人脸添加失败：" + updateFaceRes.msg);
            }


          } else {
            //获取所有人脸信息  
            var face_database = [];
            await getFace_database_all().then(response => {
              response.data.forEach(item => {
                var face = {
                  face_id: item.face_id,
                  face_embedding: item.embedding
                }
                face_database.push(face);
              });
            });
            var params = {
              face_id: this.form.faceId,
              face_database: face_database,
              images: face_Image_arr
            }
            var addFaceRes;
            try {
              // 先调用算法服务
              addFaceRes = await addFace(params);
            } catch (error) {
              console.error('调用算法服务失败:', error);
              this.$modal.msgError("调用算法服务失败，请重试");
            }
            if (addFaceRes.code === 200) {
              // 算法服务调用成功后，再保存到数据库
              if (!addFaceRes.data.success) {
                this.$modal.msgError("人脸添加失败：" + addFaceRes.data.message);
                return;
              }
              this.form.age = addFaceRes.data.age;
              this.form.gender = addFaceRes.data.gender;
              // 将二维数组转换为字符串并去掉所有空格
              this.form.faceEncoding = JSON.stringify(addFaceRes.data.embeddings).replace(/\s+/g, '');
              await addFace_database(this.form);
              this.$modal.msgSuccess("新增成功");
              this.open = false;
              this.getList();
            } else {
              this.$modal.msgError("人脸添加失败：" + addFaceRes.msg);
            }

          }
        }
      });
    },
    /** 删除按钮操作 */
    handleDelete (row) {
      const ids = row.id || this.ids;
      this.$modal.confirm('是否确认删除人脸信息，编号为"' + ids + '"的数据项？').then(function () {
        return delFace_database(ids);
      }).then(() => {
        this.getList();
        this.$modal.msgSuccess("删除成功");
      }).catch(() => { });
    },
    /** 导出按钮操作 */
    handleExport () {
      this.download('system/face_database/export', {
        ...this.queryParams
      }, `face_database_${new Date().getTime()}.xlsx`)
    },
    /** 生成唯一ID */
    generateUniqueId () {
      const timestamp = new Date().getTime();
      const random = Math.floor(Math.random() * 10000);
      return `FACE${timestamp}${random}`;
    },
    /** 修改状态 */
    handleStatusChange (row) {
      let text = row.status === 1 ? "启用" : "作废";
      this.$modal.confirm('确认要"' + text + '""' + row.userName + '"的人脸信息吗？').then(function () {
        return updateFace_database(row);
      }).then(() => {
        this.$modal.msgSuccess(text + "成功");
      }).catch(() => {
        row.status = row.status === 1 ? 0 : 1;
      });
    },
    /** 处理图片URL */
    getImageUrl (imageData) {
      if (!imageData) {
        return '';
      }
      try {
        // 检查是否是base64编码
        const base64Regex = /^([A-Za-z0-9+/]{4})*([A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{2}==)?$/;
        if (base64Regex.test(imageData)) {
          console.log(`data:image/jpeg;base64:${imageData}`);
          return `data:image/jpeg;base64:${imageData}`;
        }

        // 如果不是base64，则作为URL处理
        return imageData
      } catch (error) {
        console.error('图片数据处理失败:', error);
        return '';
      }
    },
  }
};
</script>

<style lang="scss" scoped>
/* 添加禁用输入框的样式 */
::v-deep .el-input.is-disabled .el-input__inner {
  background-color: rgba(0, 40, 85, 0.1);
  border-color: rgba(0, 149, 255, 0.2);
  color: #333333;
  cursor: not-allowed;
}

.feature-text {
  display: inline-block;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
