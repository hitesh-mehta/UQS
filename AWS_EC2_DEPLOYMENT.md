# UQS — Ultimate AWS EC2 Free Tier Deployment Guide (GitHub + Vercel Method)

Follow this extremely clear guide to host the Universal Query Solver (UQS) natively. We will split the architecture:
- **Backend API:** AWS EC2 Free Tier
- **Frontend UI:** Vercel (`https://uqs.vercel.app`)

---

## 🟢 PHASE 1: Creating the AWS EC2 Instance (Free Tier)
If you haven't created your instance exactly like this, or want to double-check:
1. Open the [AWS EC2 Console](https://console.aws.amazon.com/ec2/) and click **"Launch Instance"**.
2. **Name:** `UQS-Server`
3. **OS Image (AMI):** Select **Amazon Linux 2023** (Free tier eligible). 
   *(Note: Amazon Linux uses `ec2-user` for SSH login).*
4. **Instance Type:** Select **`t2.micro`** or **`t3.micro`** (Whichever says "Free tier eligible").
5. **Key Pair:** Create a new key-pair (e.g., `UQS.pem`), download it, and keep it safe.
6. **Network Settings:** 
   - Check "Allow SSH traffic from Anywhere"
   - Check "Allow HTTP traffic from the internet"
7. Click **Launch Instance**.

---

## 🟢 PHASE 2: Open Security Ports (Crucial)
Your instance is running, but AWS firewalls block our custom app ports by default.
1. In your EC2 Dashboard, click on your matching Instance ID and go to the **Security** tab at the bottom.
2. Click on the **Security Group** link (looks like `sg-0abc123...`).
3. Click **Edit Inbound Rules** and Add the Backend port rule:
   - **Custom TCP** | Port `8000` | Source: `Anywhere-IPv4` (0.0.0.0/0) 
4. Click **Save rules**.

---

## 🟢 PHASE 3: Push Your Code to GitHub
1. On your local PC, make sure your `.env` file is NOT being pushed! Open your `.gitignore` and ensure `.env` is listed there. 
2. Push your `UQS` folder to a new repository on GitHub (Public or Private is fine).
   ```bash
   git init
   git add .
   git commit -m "Initial commit for UQS deployment"
   git branch -M main
   git remote add origin https://github.com/YOUR_GIT_USERNAME/YOUR_REPO_NAME.git
   git push -u origin main
   ```

---

## 🟢 PHASE 4: Fetch Code & Prepare Environment on EC2
Now, SSH into your EC2 Machine using your Powershell Terminal.

```powershell
ssh -i UQS.pem ec2-user@YOUR_AWS_PUBLIC_IP
```

Once you are logged into the AWS Machine terminal, install `git`, clone your repo, and recreate the `.env` file!

```bash
# 1. Update machine and install Git
sudo dnf update -y
sudo dnf install git -y

# 2. Clone your repository
git clone https://github.com/YOUR_GIT_USERNAME/YOUR_REPO_NAME.git uqs
cd uqs

# 3. Create your secure .env file (since it was excluded from GitHub!)
nano .env
```
👉 *Inside the `nano` text editor, paste all the contents of your local PC's `.env` file (your Supabase and Gemini keys).* 
*Press `CTRL + O` to save, `Enter` to confirm, and `CTRL + X` to exit Nano.*

---

## 🟢 PHASE 5: Install Docker & Run the Backend!
Instantly get Docker running on your Amazon Linux box to host the API.

```bash
# 1. Install Docker
sudo dnf install docker -y
sudo systemctl start docker
sudo systemctl enable docker

# 2. Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.5/docker-compose-linux-x86_64" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 3. Start the Backend API
sudo docker-compose up -d --build
```
> Your backend is now officially live on AWS at `http://YOUR_AWS_PUBLIC_IP:8000`.

---

## 🟢 PHASE 6: Connect Vercel to your AWS EC2 🚀
The final step is telling your Vercel Frontend where to send questions!

1. Go to your **Vercel Dashboard**.
2. Open your `UQS` project and go to **Settings** -> **Environment Variables**.
3. Add a new variable:
   - **Key:** `BACKEND_API_URL`
   - **Value:** `http://YOUR_AWS_PUBLIC_IP:8000` (Replace with your literal EC2 IP).
4. Remove `NEXT_PUBLIC_API_URL` if you created it earlier.
5. Click **Save** and trigger a redeploy on Vercel.

**Access your app!**
Visit **`https://uqs.vercel.app`** and the whole pipeline will integrate beautifully. The CORS policy is already unlocked to accept your exact Vercel link!
