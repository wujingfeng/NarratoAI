<?php
namespace oss;

use app\common\esimages\model\EsImagesModel;
use Exception;
use GuzzleHttp\Client;
use OSS\OssClient;
use OSS\Core\OssException;
use think\facade\Log;
use Utils;
use uuer\HttpClient;

/**
 * Oss
 */
class Oss{
    const BucketKeyList = [
        'ALIOSS',
        'USER_ALIOSS',
    ];
    /**
     * 上传文件
     */
    public static function UploadFile($filename,$ossFilename,$envKey="ALIOSS"){
        $accessKeyId = env("{$envKey}.AccessKeyId");
        $accessKeySecret = env("{$envKey}.AccessKeySecret");
        // Endpoint以杭州为例，其它Region请按实际情况填写。
        $endpoint = env("{$envKey}.Endpoint");
        // 填写Bucket名称，例如examplebucket。
        $bucket = env("{$envKey}.Bucket");
        if(!is_file($filename)){
            return false;
        }
        try {
            $ossFilename = ltrim($ossFilename,'/');
            $ossClient = new OssClient($accessKeyId, $accessKeySecret, $endpoint);
            $ossClient->uploadFile($bucket, $ossFilename, $filename);
            return env("{$envKey}.CDNURL").$ossFilename;
        } catch (Exception $e) {
            Log::error("UploadFile阿里云OSS文件上传失败：filename={$filename},ossFilename={$ossFilename},errmsg=".$e->getMessage());
            return false;
        }
    }

    /**
     * 将base64文件上传到阿里云oss
     */
    public static function uploadBase64ToOSS($base64Data, $ossFilename)
    {
        // 1. 处理Base64数据
        if (preg_match('/^data:image\/(\w+);base64,/', $base64Data, $matches)) {
            $base64Data = substr($base64Data, strpos($base64Data, ',') + 1);
        }
        $imageData = base64_decode($base64Data);
        $tempFilePath = runtime_path() . '/baseTmp' . uniqid() . '.png';
        file_put_contents($tempFilePath, $imageData);

        $result = self::UploadFile($tempFilePath, $ossFilename);

        // 4. 清理临时文件
        if (file_exists($tempFilePath)) {
            unlink($tempFilePath);
        }
        return $result;
    }

    /**
     * 删除文件
     */
    public static function DeleteFile($url,$envKey="ALIOSS"){
        $urls = [
            'https://gamecdn.beiyinapp.com/inchat/image/violation_img.png',
            'https://gamecdn.beiyinapp.com/inchat/image/violation_video.png',
            'https://gamecdn.beiyinapp.com/inchat/image/expire_img.mp4',
            'https://gamecdn.beiyinapp.com/inchat/image/expire_img.png',
            'https://gamecdn.beiyinapp.com/inchat/image/fail_img.png',
            'https://gamecdn.beiyinapp.com/temp/2025425risk_image.png',
        ];
        if(in_array($url,$urls)){
            return false;
        }
        $image = EsImagesModel::where('url',$url)->where('status',1)->find();
        if($image){//图库里面的图片不能删除
            return false;
        }
        $accessKeyId = env("{$envKey}.AccessKeyId");
        $accessKeySecret = env("{$envKey}.AccessKeySecret");
        // Endpoint以杭州为例，其它Region请按实际情况填写。
        $endpoint = env("{$envKey}.Endpoint");
        // 填写Bucket名称，例如examplebucket。
        $bucket= env("{$envKey}.Bucket");
        $info = parse_url($url);
        try{
            $ossClient = new OssClient($accessKeyId, $accessKeySecret, $endpoint);
            $ossClient->deleteObject($bucket,trim($info['path'],'/'));
            return true;
        }catch(\Exception $e){
            return false;
        }
    }
    /**
     * 文件是否存在
     */
    public static function fileExist($url,$envKey="ALIOSS"){
        $accessKeyId = env("{$envKey}.AccessKeyId");
        $accessKeySecret = env("{$envKey}.AccessKeySecret");
        // Endpoint以杭州为例，其它Region请按实际情况填写。
        $endpoint = env("{$envKey}.Endpoint");
        // 填写Bucket名称，例如examplebucket。
        $bucket= env("{$envKey}.Bucket");
        $info = parse_url($url);
        try{
            $ossClient = new OssClient($accessKeyId, $accessKeySecret, $endpoint);
            return !!$ossClient->doesObjectExist($bucket,trim($info['path'],'/'));
        }catch(\Exception $e){var_dump($e->getTraceAsString());
            return false;
        }
    }

    public static function getFileMeta($filepath, $envKey="ALIOSS", $options = null)
    {
        $accessKeyId = env("{$envKey}.AccessKeyId");
        $accessKeySecret = env("{$envKey}.AccessKeySecret");
        // Endpoint以杭州为例，其它Region请按实际情况填写。
        $endpoint = env("{$envKey}.Endpoint");
        // 填写Bucket名称，例如examplebucket。
        $bucket= env("{$envKey}.Bucket");
        try{
            $ossClient = new OssClient($accessKeyId, $accessKeySecret, $endpoint);
            return $ossClient->getObjectMeta($bucket, $filepath, $options);
        }catch(\Exception $e){
            return false;
        }
    }

    public static function listObject($prefixPath = '', $envKey="ALIOSS", $option = [])
    {
        $accessKeyId = env("{$envKey}.AccessKeyId");
        $accessKeySecret = env("{$envKey}.AccessKeySecret");
        // Endpoint以杭州为例，其它Region请按实际情况填写。
        $endpoint = env("{$envKey}.Endpoint");
        // 填写Bucket名称，例如examplebucket。
        $bucket= env("{$envKey}.Bucket");
        $CDNURL = env("{$envKey}.CDNURL");
        try{
            $ossClient = new OssClient($accessKeyId, $accessKeySecret, $endpoint);
            // $option = [];
            if ($prefixPath) {
                $option['prefix'] = $prefixPath;
            }
            $resp = $ossClient->listObjectsV2($bucket,$option ?? null);
            $objects = $resp->getObjectList();
            $filePaths = [];
            foreach ($objects as $object) {
                $filePath = $object->getKey();
//                if (str_contains($filePath, '.DS_Store')) {
//                    continue;
//                }
                $filePaths[] = $CDNURL . $filePath;
            }
            return $filePaths;
        }catch(\Exception $e){
            return false;
        }
    }
    /**
     * H5上传文件
     */
    public static function H5Upload($ossFilename,$size=0,array $contentType = ["image/jpg", "image/jpeg", "image/png"],$envKey="ALIOSS"){
        $accessKeyId = env("{$envKey}.TempAccessKeyId");
        $accessKeySecret = env("{$envKey}.TempAccessKeySecret");
        // Endpoint以杭州为例，其它Region请按实际情况填写。
        $endpoint = env("{$envKey}.Endpoint");
        // 填写Bucket名称，例如examplebucket。
        $bucket= env("{$envKey}.Bucket");
        $policy = [
            'expiration'=>str_replace(' ','T',date('Y-m-d H:i:s',time()-8*3600+120).'.000Z'),
            'conditions'=>[
                [
                    'bucket'=>$bucket,
                ],
                ['content-length-range',1,$size?$size:1024*1024*200],
                // ["eq", "\$success_action_status", "200"],
                ["eq", "\$key",$ossFilename],
                ["in", "\$content-type", $contentType],
            ],
        ];
        $policy = base64_encode(json_encode($policy,JSON_UNESCAPED_UNICODE));
        return [
            'OSSAccessKeyId'=>$accessKeyId,
            'policy'=>$policy,
            'key'=>$ossFilename,
            'url'=>env("{$envKey}.URL"),
            'Signature'=>base64_encode(hash_hmac('sha1',$policy,$accessKeySecret,true)),
            'object_url'=>rtrim(env("{$envKey}.CDNURL"),'/')."/{$ossFilename}",
        ];
    }

    /**
     * 将远程文件上传到oss
     *
     * @param          $fileUrl
     * @param          $ossFilename
     * @param  string  $envKey
     * @param  bool     $needCompress 是否需要图片压缩
     * @param  bool     $download 使用那种下载方式 1默认下载 2命令行下载
     *
     * @return bool|string
     * @author         吴靖丰
     * @date           2023/9/14
     * @time           15:59
     */
    public static function UploadFileRemoteFile($fileUrl, $ossFilename, $envKey="USER_ALIOSS", bool $needCompress = false, int $download = 1): bool|string
    {
		$path = parse_url($fileUrl, PHP_URL_PATH);
        $filename = runtime_path().basename($path);
        if(!is_file($filename)){
            if ($download == 2) {
                $err = HttpClient::downloadByLine($fileUrl, $filename);
                if (!$err) {
                    return $err;
                }
            } else {
                $err = HttpClient::download($fileUrl,$filename);
                if(!$err){
                    return $err;
                }
            }

//            $client = new Client();
//            $response = $client->get($fileUrl, ['sink' => $filename]);
//            if ($response->getStatusCode() !== 200) {
//                return "资源下载失败";
//            }
            // 是否需要压缩图片
            if ($needCompress) {
                $outfilePath = runtime_path() . pathinfo($filename, PATHINFO_FILENAME) . '.jpeg';
                $res = Utils::compressImage($filename, $outfilePath);
                if ($res) {
                    // 如果压缩成功, 则将之前的文件删除
                    @unlink($filename);
                    // 如果压缩成功, 则将上传的文件地址替换为压缩后的图片地址
                    $filename = $outfilePath;
                    $ossFilename = pathinfo($ossFilename, PATHINFO_DIRNAME) . '/' . pathinfo($ossFilename, PATHINFO_FILENAME) . '.jpeg';
                }
            }
        }
//        $ossFilename = "/inchat/image/square/".basename($fileUrl);
        $result = self::UploadFile($filename,$ossFilename, $envKey);
        @unlink($filename);
        return $result;

    }
    /**
     * 根据URL获取Bucket
     */
    public static function getBucketByUrl($url){
        $url = strval($url);
        if(stripos($url,'https://gamecdn.beiyinapp.com/')===0||stripos($url,'http://gamecdn.beiyinapp.com/')===0){
            return 'ALIOSS';
        }else if(stripos($url,'http://inchat-upload.oss-cn-shanghai.aliyuncs.com/')===0||stripos($url,'https://inchat-upload.oss-cn-shanghai.aliyuncs.com/')===0){
            return 'USER_ALIOSS';
        }else if(stripos($url,'http://inchatcdn.beiyinapp.com/')===0||stripos($url,'https://inchatcdn.beiyinapp.com/')===0){
            return 'USER_ALIOSS';
        }
    }
}