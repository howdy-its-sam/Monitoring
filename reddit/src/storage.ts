import { S3Client, PutObjectCommand, GetObjectCommand } from "@aws-sdk/client-s3";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "fs";
import { join } from "path";
import { Readable } from "stream";

export class StorageDriver {
  private s3: S3Client | null = null;
  private bucket: string = "";
  private useS3: boolean = false;
  private localDir: string = "";

  constructor() {
    if (process.env.USE_S3 === "true") {
      this.useS3 = true;
      this.bucket = process.env.BUCKET_NAME || "reddit-monitor";
      this.s3 = new S3Client({
        region: process.env.AWS_REGION || "auto",
        endpoint: process.env.AWS_ENDPOINT, // Critical for R2/MinIO
        forcePathStyle: true, // Required for Railway/MinIO
        credentials: {
          accessKeyId: process.env.AWS_ACCESS_KEY_ID!,
          secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY!
        }
      });
      console.log(`📦 Storage: S3 Bucket '${this.bucket}'`);
    } else {
      this.localDir = process.env.DATA_DIR || join(process.cwd(), "reddit/data");
      if (!existsSync(this.localDir)) mkdirSync(this.localDir, { recursive: true });
      console.log(`📦 Storage: Local Disk '${this.localDir}'`);
    }
  }

  public async save(key: string, data: string): Promise<void> {
    if (this.useS3 && this.s3) {
      await this.s3.send(new PutObjectCommand({
        Bucket: this.bucket,
        Key: key,
        Body: data,
        ContentType: "application/json"
      }));
    } else {
      writeFileSync(join(this.localDir, key), data);
    }
  }

  public async load(key: string): Promise<string | null> {
    if (this.useS3 && this.s3) {
      try {
        const command = new GetObjectCommand({ Bucket: this.bucket, Key: key });
        const response = await this.s3.send(command);
        return await response.Body?.transformToString() || null;
      } catch (e: any) {
        if (e.name === "NoSuchKey") return null;
        console.error(`S3 Load Error: ${e}`);
        return null;
      }
    } else {
      const path = join(this.localDir, key);
      if (existsSync(path)) return readFileSync(path, "utf-8");
      return null;
    }
  }
}
