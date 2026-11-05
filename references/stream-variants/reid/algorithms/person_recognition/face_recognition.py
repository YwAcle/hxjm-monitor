import cv2
import numpy as np
import base64
from typing import Dict, Any, List, Optional
import time
import json
import logging
from db.database import get_db, FaceDatabase
from datetime import datetime
from db.face_database_manager import face_database_manager  # 导入实例而不是类

# 导入模型管理器
from models import model_manager, get_model_context

# 配置日志
logger = logging.getLogger(__name__)


class FaceRecognizer:
    def __init__(self, imgsz: int = 640):
        """初始化人脸识别器"""
        # 检查并启用GPU
        self.use_gpu = False
        try:
            import torch
            if torch.cuda.is_available():
                self.use_gpu = True
                self.device = 'cuda'
                # 输出GPU信息
                logger.info(f"检测到GPU，启用硬件加速。当前GPU: {torch.cuda.get_device_name(0)}")
            else:
                self.device = 'cpu'
                logger.info("未检测到GPU，使用CPU模式")
        except Exception as e:
            logger.error(f"GPU初始化失败: {str(e)}, 使用CPU模式")
            self.device = 'cpu'

        # 绑定InsightFace模型
        self.face_analyzer = None
        self.need_release = False

        # 存储已知人脸的特征
        self.known_face_embeddings = []
        self.known_face_ids = []
        # 调整相似度阈值
        self.similarity_threshold = 0.4  # 识别阈值
        self.min_face_size = 100  # 最小人脸尺寸
        self.max_face_count = 10  # 单张图片最大处理人脸数

        # 模型配置
        self.imgsz = imgsz
        self.model_id = ""

    def __del__(self):
        """析构函数，确保释放模型资源"""
        if self.model_id:
            try:
                model_manager.release_model(self.model_id)
                self.model_id = ""
                self.face_analyzer = None
            except Exception as e:
                logger.error(f"释放人脸识别模型失败: {e}")

    def _get_face_analyzer(self):
        """获取人脸分析器模型"""
        if self.face_analyzer is not None:
            return self.face_analyzer

        # 使用上下文管理器获取模型
        config = {
            "name": "buffalo_l",
            "det_size": (self.imgsz, self.imgsz)
        }

        try:
            model, model_id = model_manager.get_model("face_recognition", config, self.device)
            if model is None:
                logger.error("加载人脸识别模型失败")
                return None

            self.face_analyzer = model
            self.model_id = model_id
            return self.face_analyzer

        except Exception as e:
            logger.error(f"获取人脸分析器失败: {e}")
            return None

    def recognize(self, images: List[str], machine_id: Optional[str] = None) -> Dict[str, Any]:
        """
        识别图片中的人脸

        Args:
            images: base64编码的图片列表
            machine_id: 设备ID，用于日志
        """
        try:
            print("1",images)
            if not images:
                return {
                    "success": False,
                    "message": "未提供图片"
                }

            # 获取人脸分析器
            face_analyzer = self._get_face_analyzer()
            if face_analyzer is None:
                return {
                    "success": False,
                    "message": "人脸分析器初始化失败"
                }

            results = []
            face_embeddings = []  # 存储所有图片的特征向量
            # 第一步：提取所有图片的特征向量
            for idx, image_base64 in enumerate(images):
                try:
                    # 解码图片
                    img_data = base64.b64decode(image_base64)
                    nparr = np.frombuffer(img_data, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    # 检测人脸
                    faces = face_analyzer.get(img)
                    if not faces:
                        return {
                            "success": False,
                            "message": "未检测到人脸"
                        }

                    if len(faces) > 1:
                        return {
                            "success": False,
                            "message": "检测到多个人脸"
                        }

                    # 保存特征向量
                    face_embeddings.append({
                        "idx": idx,
                        "embedding": faces[0].embedding,
                        "quality": float(faces[0].det_score),
                        "age": int(faces[0].age),
                        "gender": faces[0].gender
                    })
                except Exception as e:
                    logger.error(f"处理图片{idx + 1}失败: {str(e)}")
                    continue

            if not face_embeddings:
                return {
                    "success": False,
                    "message": "未能提取到有效的人脸特征"
                }

            # 第二步：获取人脸特征库
            face_database = face_database_manager.get_face_features()
            if not face_database:
                logger.warning("人脸特征库为空，正在尝试主动加载...")
                # 尝试立即更新特征库
                success = face_database_manager.update_face_features()
                if success:
                    face_database = face_database_manager.get_face_features()
                    logger.info(f"已加载人脸特征库，共 {len(face_database)} 条记录")
                else:
                    logger.error("人脸特征库更新失败，请检查数据库连接")

                # 再次检查特征库
                if not face_database:
                    # 输出更多诊断信息
                    try:
                        from db.query import query_faces
                        faces = query_faces()
                        logger.error(f"数据库查询结果: {len(faces)} 条记录")
                        if faces and len(faces) > 0:
                            logger.error(f"数据库中存在记录但未能加载到特征库，可能是格式问题")
                            # 输出第一条记录的信息，帮助诊断
                            sample = faces[0]
                            logger.error(f"示例记录 ID:{sample.face_id}, 格式类型:{type(sample.face_encoding)}")
                    except Exception as db_err:
                        logger.error(f"尝试直接查询数据库时出错: {db_err}")

                    return {
                        "success": False,
                        "message": "人脸特征库为空，无法进行匹配",
                        "error_code": "EMPTY_FACE_DATABASE"
                    }

            # 第三步：与人脸库比对
            matches = []
            for face_data in face_embeddings:
                face_embedding = face_data["embedding"]  # 获取当前处理的人脸特征

                best_match = None
                best_similarity = 0

                # 与特征库中的每个人脸进行比对
                for known_face in face_database:
                    if 'face_encoding' not in known_face:
                        continue

                    # 获取存储的特征向量
                    known_embedding = known_face['face_encoding']

                    if isinstance(known_embedding, list):
                        # 如果是嵌套列表，取第一个特征向量
                        if known_embedding and isinstance(known_embedding[0], list):
                            known_embedding = known_embedding[0]

                    try:
                        known_embedding_arr = np.array(known_embedding).squeeze()

                        # 如果维度还是不正确，跳过
                        if known_embedding_arr.ndim != 1:
                            logger.error(f"known_embedding shape 异常: {known_embedding_arr.shape}")
                            continue

                        similarity = float(
                            np.dot(face_embedding, known_embedding_arr) /
                            (np.linalg.norm(face_embedding) * np.linalg.norm(known_embedding_arr))
                        )

                        if similarity > self.similarity_threshold and similarity > best_similarity:
                            best_similarity = similarity
                            best_match = {
                                "face_id": known_face['face_id'],
                                "confidence": similarity,
                                "age": face_data["age"],
                                "gender": "male" if face_data["gender"] == 1 else "female",
                                "quality": face_data["quality"]
                            }

                    except Exception as e:
                        logger.error(f"计算相似度失败: {str(e)}")
                        continue

                if best_match:
                    matches.append(best_match)
                else:
                    logger.info(f'best_similarity: {best_similarity}')
                    if best_similarity < 0.1:
                        # 未匹配到已知人脸，尝试添加为陌生人
                        unknown_match = self._add_unknown_face(
                            face_embedding=face_data["embedding"],
                            age=face_data["age"],
                            gender=face_data["gender"],
                            quality=face_data["quality"],
                            face_image=images[idx]
                        )
                        if unknown_match:
                            matches.append(unknown_match)

                            # 返回结果
            return {
                "success": True,
                "matches": matches,
                "count": len(matches)
            }

        except Exception as e:
            logger.error(f"人脸识别失败: {str(e)}")
            return {
                "success": False,
                "message": f"人脸识别失败: {str(e)}",
                "matches": [],
                "count": 0
            }
        finally:
            # 如果使用了临时模型，释放它
            if self.need_release and self.model_id:
                model_manager.release_model(self.model_id)
                self.face_analyzer = None
                self.model_id = ""
                self.need_release = False

    # 添加人脸
    def add_face(self, face_id: str, images: List[str], face_database: List[Dict]) -> Dict[str, Any]:
        """
        提取多张图片的人脸特征

        Args:
            face_id: 人脸ID
            images: base64编码的人脸图片列表
            face_database: 现有的人脸特征数据库
        Returns:
            Dict: 包含人脸特征的结果
        """
        try:
            if not images:
                return {
                    "success": False,
                    "message": "未提供图片"
                }

            # 获取人脸分析器
            face_analyzer = self._get_face_analyzer()
            if face_analyzer is None:
                return {
                    "success": False,
                    "message": "人脸分析器初始化失败"
                }

            results = []
            result_embeddings = []
            face_embeddings = []  # 存储所有图片的特征向量

            # 第一步：提取所有图片的特征向量
            for idx, image_base64 in enumerate(images):
                # 解码图片
                img_data = base64.b64decode(image_base64)
                nparr = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                # 检测人脸
                faces = face_analyzer.get(img)
                if not faces:
                    results.append({
                        "success": False,
                        "message": f"图片{idx + 1}未检测到人脸"
                    })
                    continue

                if len(faces) > 1:
                    results.append({
                        "success": False,
                        "message": f"图片{idx + 1}包含多个人脸"
                    })
                    continue

                # 保存特征向量
                face_embeddings.append({
                    "idx": idx,
                    "embedding": faces[0].embedding,
                    "quality": float(faces[0].det_score),
                    "age": int(faces[0].age),
                    "gender": faces[0].gender
                })

            # 第二步：检查所有图片是否为同一个人
            if len(face_embeddings) > 1:
                for i in range(len(face_embeddings)):
                    for j in range(i + 1, len(face_embeddings)):
                        similarity = float(np.dot(face_embeddings[i]["embedding"], face_embeddings[j]["embedding"]) / (
                                np.linalg.norm(face_embeddings[i]["embedding"]) * np.linalg.norm(
                            face_embeddings[j]["embedding"])
                        ))

                        if similarity < self.similarity_threshold:
                            return {
                                "success": False,
                                "message": f"图片{face_embeddings[i]['idx'] + 1}和图片{face_embeddings[j]['idx'] + 1}不是同一个人",
                                "similarity": similarity
                            }
            # 第三步：与人脸库比对
            for face_data in face_embeddings:
                face_embedding = face_data["embedding"]  # 获取当前处理的人脸特征
                idx = face_data["idx"]

                is_duplicate = False
                # 检查是否已存在相同的人脸
                if face_database:
                    for known_face in face_database:
                        if 'face_embedding' not in known_face:
                            continue

                        # 获取当前人的所有人脸特征
                        embeddings = known_face['face_embedding']
                        if isinstance(embeddings, str):
                            try:
                                embeddings = json.loads(embeddings)
                            except Exception as e:
                                logger.error(f"解析特征向量数组失败: {str(e)}")
                                continue

                        # 确保是列表格式
                        if not isinstance(embeddings, list):
                            continue

                        # 与该人所有人脸特征进行比对
                        try:
                            for stored_embedding in embeddings:
                                known_embedding = np.array(stored_embedding)
                                # 确保两个向量的维度匹配
                                if known_embedding.shape != face_embedding.shape:
                                    continue

                                # 计算余弦相似度
                                similarity = float(np.dot(face_embedding, known_embedding) / (
                                        np.linalg.norm(face_embedding) * np.linalg.norm(known_embedding)
                                ))

                                # 如果相似度超过阈值，说明是同一个人
                                if similarity > self.similarity_threshold:
                                    results.append({
                                        "success": False,
                                        "message": f"图片{idx + 1}的人脸与ID为{known_face['face_id']}的人脸重复",
                                        "similar_face_id": known_face['face_id'],
                                        "similarity": similarity
                                    })
                                    is_duplicate = True
                                    break

                            if is_duplicate:
                                break

                        except Exception as e:
                            logger.error(f"比对人脸特征时出错: {str(e)}")
                            continue

                if is_duplicate:
                    continue

                # 如果没有重复，添加到结果中
                result_embeddings.append(face_embedding.tolist())
                results.append({
                    "success": True,
                    "message": f"图片{idx + 1}人脸特征提取成功",
                    "face_id": face_id,
                    "embedding": face_embedding.tolist(),
                    "quality": float(face_data["quality"]),
                    "age": int(face_data["age"]),
                    "gender": int(face_data["gender"])
                })

            # 返回结果
            success_results = [r for r in results if r["success"]]
            if not success_results:
                # 检查是否有任何结果
                if not results:
                    return {
                        "success": False,
                        "message": "未能提取任何人脸特征",
                        "details": "所有图片处理失败"
                    }
                else:
                    # 返回第一个失败的原因
                    return {
                        "success": False,
                        "message": results[0]["message"],
                        "details": results
                    }

            # 从成功结果中找出quality最高的人脸
            best_face = max(success_results, key=lambda x: x["quality"])

            return {
                "success": True,
                "quality": best_face['quality'],
                "message": f"成功提取{len(success_results)}张图片的人脸特征",
                "embeddings": result_embeddings,
                "age": int(best_face["age"]),
                "gender": int(best_face["gender"]),
                "failed": [r for r in results if not r["success"]]
            }

        except Exception as e:
            raise Exception(f"人脸特征提取失败: {str(e)}")
        finally:
            # 如果使用了临时模型，释放它
            if self.need_release and self.model_id:
                model_manager.release_model(self.model_id)
                self.face_analyzer = None
                self.model_id = ""
                self.need_release = False

    def update_face_face_id(self, face_id: str, images: List[str]) -> Dict[str, Any]:
        """
        更新数据库中某个 face_id 的人脸特征
        1. 提取所有图片 embedding
        2. 确认是同一个人
        3. 写入数据库（覆盖旧 embedding）
        """

        if not images:
            return {"success": False, "message": "没有提供图片"}

        # 1. 获取 face analyzer
        face_analyzer = self._get_face_analyzer()
        if face_analyzer is None:
            return {"success": False, "message": "人脸分析器初始化失败"}

        embeddings = []

        # 2. 提取 embedding
        for idx, img_b64 in enumerate(images):
            try:
                img_data = base64.b64decode(img_b64)
                img = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)

                faces = face_analyzer.get(img)
                if not faces:
                    return {"success": False, "message": f"第{idx + 1}张图片未检测到人脸"}

                if len(faces) > 1:
                    return {"success": False, "message": f"第{idx + 1}张图片检测到多人脸"}

                embeddings.append(faces[0].embedding)

            except Exception as e:
                return {"success": False, "message": f"图片{idx + 1}处理失败:{str(e)}"}

        # 3. 检查是否为同一人
        if len(embeddings) > 1:
            for i in range(len(embeddings)):
                for j in range(i + 1, len(embeddings)):
                    sim = float(np.dot(embeddings[i], embeddings[j]) /
                                (np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j])))

                    if sim < self.similarity_threshold:
                        return {
                            "success": False,
                            "message": f"图片 {i + 1} 和图片 {j + 1} 属于不同人",
                            "similarity": sim
                        }

        # ============================
        # 4. 写入数据库（使用 ORM 的 query.update）
        # ============================
        db = get_db()
        try:
            new_encoding_json = json.dumps([emb.tolist() for emb in embeddings])
            print("new_encoding_json type =", type(new_encoding_json))
            print("new_encoding_json =", new_encoding_json)
            # 👇 强制转成 bytes，才能写入 BLOB
            face_encoding_bytes = new_encoding_json.encode("utf-8")
            # 执行批量更新（性能更高）
            rows = db.query(FaceDatabase).filter(
                FaceDatabase.face_id == face_id
            ).update(
                {
                    FaceDatabase.face_encoding: face_encoding_bytes,
                    FaceDatabase.status: 1,
                    FaceDatabase.quality: faces[0]["det_score"],
                    FaceDatabase.update_time: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
                synchronize_session=False
            )

            if rows == 0:
                return {"success": False, "message": f"face_id={face_id} 不存在"}
            face_database_manager.update_face_features() # 更新内存
            db.commit()

        except Exception as e:
            db.rollback()
            return {"success": False, "message": f"数据库更新失败: {str(e)}"}

        finally:
            db.close()

        # ============================
        # 返回更新成功结果
        # ============================
        return {
            "success": True,
            "message": f"成功更新 face_id={face_id} 的人脸特征",
            "embeddings": [emb.tolist() for emb in embeddings]
        }

    # 修改人脸
    def update_face(self, images: List[str]) -> Dict[str, Any]:
        """
        修改人脸特征 - 提取新图片的人脸特征

        Args:
            images: base64编码的人脸图片列表
        Returns:
            Dict: 包含人脸特征的结果
        """
        try:
            print("3", images)
            if not images:
                return {
                    "success": False,
                    "message": "未提供图片"
                }

            # 获取人脸分析器
            face_analyzer = self._get_face_analyzer()
            if face_analyzer is None:
                return {
                    "success": False,
                    "message": "人脸分析器初始化失败"
                }

            results = []
            result_embeddings = []
            face_embeddings = []  # 存储所有图片的特征向量

            # 第一步：提取所有图片的特征向量
            for idx, image_base64 in enumerate(images):
                try:
                    # 解码图片
                    img_data = base64.b64decode(image_base64)
                    nparr = np.frombuffer(img_data, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    # 检测人脸
                    faces = face_analyzer.get(img)

                    if not faces:
                        results.append({
                            "success": False,
                            "message": f"图片{idx + 1}未检测到人脸"
                        })
                        continue

                    if len(faces) > 1:
                        results.append({
                            "success": False,
                            "message": f"图片{idx + 1}包含多个人脸"
                        })
                        continue

                    # 保存特征向量
                    face_embeddings.append({
                        "idx": idx,
                        "embedding": faces[0].embedding,
                        "quality": float(faces[0].det_score),
                        "age": int(faces[0].age),
                        "gender": faces[0].gender
                    })

                except Exception as e:
                    logger.error(f"处理图片{idx + 1}时出错: {str(e)}")
                    results.append({
                        "success": False,
                        "message": f"图片{idx + 1}处理失败: {str(e)}"
                    })
                    continue

            # 第二步：检查所有图片是否为同一个人
            if len(face_embeddings) > 1:
                for i in range(len(face_embeddings)):
                    for j in range(i + 1, len(face_embeddings)):
                        similarity = float(np.dot(face_embeddings[i]["embedding"], face_embeddings[j]["embedding"]) / (
                                np.linalg.norm(face_embeddings[i]["embedding"]) * np.linalg.norm(
                            face_embeddings[j]["embedding"])
                        ))

                        if similarity < self.similarity_threshold:
                            return {
                                "success": False,
                                "message": f"图片{face_embeddings[i]['idx'] + 1}和图片{face_embeddings[j]['idx'] + 1}不是同一个人",
                                "similarity": similarity
                            }

            # 第三步：添加所有特征向量到结果中
            for face_data in face_embeddings:
                result_embeddings.append(face_data["embedding"].tolist())
                results.append({
                    "success": True,
                    "message": f"图片{face_data['idx'] + 1}人脸特征提取成功",
                    "embedding": face_data["embedding"].tolist(),
                    "quality": float(face_data["quality"]),
                })

            # 返回结果
            success_results = [r for r in results if r["success"]]
            if not success_results:
                if not results:
                    return {
                        "success": False,
                        "message": "未能提取任何人脸特征",
                        "details": "所有图片处理失败"
                    }
                else:
                    return {
                        "success": False,
                        "message": results[0]["message"],
                        "details": results
                    }

            return {
                "success": True,
                "message": f"成功提取{len(success_results)}张图片的人脸特征",
                "embeddings": result_embeddings,
                "failed": [r for r in results if not r["success"]]
            }

        except Exception as e:
            logger.error(f"修改人脸特征失败: {str(e)}")
            raise Exception(f"修改人脸特征失败: {str(e)}")
        finally:
            # 如果使用了临时模型，释放它
            if self.need_release and self.model_id:
                model_manager.release_model(self.model_id)
                self.face_analyzer = None
                self.model_id = ""
                self.need_release = False

    def _add_unknown_face(self, face_embedding: np.ndarray, age: int, gender: int, quality: float,
                          face_image: str) -> Dict:
        """添加未知人脸到数据库"""
        try:
            # 生成唯一的face_id
            face_id = f"FACE_{int(time.time())}"
            # 生成陌生人名称
            stranger_name = f"陌生人_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # 将face_embedding转换为二维数组格式的JSON字符串，然后编码为二进制
            face_encoding_json = json.dumps([face_embedding.tolist()])  # 包装为二维数组
            face_encoding_binary = face_encoding_json.encode('utf-8')

            # 添加到数据库
            db = get_db()
            try:
                new_face = FaceDatabase(
                    face_id=face_id,
                    user_name=stranger_name,
                    face_encoding=face_encoding_binary,  # 使用编码后的二进制数据
                    face_image=face_image.encode('utf-8'),  # 将base64字符串编码为二进制
                    status=1,
                    create_time=datetime.now(),
                    gender=gender,
                    age=age,
                    quality=quality
                )
                db.add(new_face)
                db.commit()

                # 更新人脸特征库
                face_database_manager.update_face_features()

                return {
                    "face_id": face_id,
                    "confidence": 1.0,
                    "age": age,
                    "gender": "male" if gender == 1 else "female",
                    "quality": quality,
                    "is_stranger": True
                }

            except Exception as e:
                db.rollback()
                logger.error(f"添加陌生人失败: {str(e)}")
                return None
            finally:
                db.close()

        except Exception as e:
            logger.error(f"添加未知人脸失败: {str(e)}")
            return None  