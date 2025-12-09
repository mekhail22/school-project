<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تسجيل الدخول</title>
    <style>
        * {
            box-sizing: border-box;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        body {
            background-color: #f5f7fa;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            color: #333;
        }
        
        .login-container {
            background-color: white;
            border-radius: 16px;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.08);
            width: 100%;
            max-width: 450px;
            padding: 40px;
            text-align: center;
        }
        
        h1 {
            color: #2c3e50;
            margin-bottom: 40px;
            font-size: 28px;
            font-weight: 700;
        }
        
        .input-group {
            margin-bottom: 25px;
            text-align: right;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #2c3e50;
            font-size: 16px;
        }
        
        /* تحسين حقول الإدخال لتبدو أكبر وأوضح */
        input {
            width: 100%;
            padding: 16px 18px;
            border: 2px solid #e0e6ed;
            border-radius: 10px;
            font-size: 17px;
            transition: all 0.3s ease;
            background-color: #f8fafc;
        }
        
        /* التركيز على الحقل النشط */
        input:focus {
            outline: none;
            border-color: #4a6cf7;
            box-shadow: 0 0 0 3px rgba(74, 108, 247, 0.1);
            background-color: white;
        }
        
        /* تخصيص حقل كلمة المرور */
        .password-input {
            letter-spacing: 2px;
            font-size: 18px;
        }
        
        /* زر تسجيل الدخول */
        .login-btn {
            background-color: #4a6cf7;
            color: white;
            border: none;
            border-radius: 10px;
            padding: 18px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            transition: background-color 0.3s ease;
            margin-top: 10px;
        }
        
        .login-btn:hover {
            background-color: #3a5ce5;
        }
        
        .forgot-password {
            display: block;
            margin-top: 20px;
            color: #4a6cf7;
            text-decoration: none;
            font-size: 15px;
        }
        
        .forgot-password:hover {
            text-decoration: underline;
        }
        
        .divider {
            display: flex;
            align-items: center;
            margin: 30px 0;
            color: #94a3b8;
        }
        
        .divider::before, .divider::after {
            content: "";
            flex: 1;
            height: 1px;
            background-color: #e2e8f0;
        }
        
        .divider span {
            padding: 0 15px;
            font-size: 14px;
        }
        
        .social-login {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin-top: 20px;
        }
        
        .social-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background-color: #f1f5f9;
            border: 1px solid #e2e8f0;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .social-btn:hover {
            background-color: #e2e8f0;
            transform: translateY(-2px);
        }
        
        .signup-link {
            margin-top: 30px;
            color: #64748b;
            font-size: 15px;
        }
        
        .signup-link a {
            color: #4a6cf7;
            text-decoration: none;
            font-weight: 600;
        }
        
        .signup-link a:hover {
            text-decoration: underline;
        }
        
        /* تأثيرات للوضوح */
        .input-group:hover label {
            color: #4a6cf7;
        }
        
        /* تحسين للموبايل */
        @media (max-width: 480px) {
            .login-container {
                padding: 30px 25px;
                margin: 20px;
            }
            
            h1 {
                font-size: 24px;
            }
            
            input {
                padding: 15px;
                font-size: 16px;
            }
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>تسجيل الدخول</h1>
        
        <form id="loginForm">
            <div class="input-group">
                <label for="username">اسم المستخدم أو البريد الإلكتروني</label>
                <input type="text" id="username" placeholder="أدخل اسم المستخدم أو بريدك الإلكتروني" autocomplete="username">
            </div>
            
            <div class="input-group">
                <label for="password">كلمة المرور</label>
                <input type="password" id="password" class="password-input" placeholder="أدخل كلمة المرور" autocomplete="current-password">
            </div>
            
            <button type="submit" class="login-btn">تسجيل الدخول</button>
            
            <a href="#" class="forgot-password">هل نسيت كلمة المرور؟</a>
        </form>
        
        <div class="divider">
            <span>أو سجل الدخول باستخدام</span>
        </div>
        
        <div class="social-login">
            <div class="social-btn">
                <span style="color: #DB4437; font-weight: bold;">G</span>
            </div>
            <div class="social-btn">
                <span style="color: #4267B2; font-weight: bold;">f</span>
            </div>
            <div class="social-btn">
                <span style="color: #1DA1F2; font-weight: bold;">𝕏</span>
            </div>
        </div>
        
        <div class="signup-link">
            ليس لديك حساب؟ <a href="#">إنشاء حساب جديد</a>
        </div>
    </div>

    <script>
        document.getElementById('loginForm').addEventListener('submit', function(event) {
            event.preventDefault();
            
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            
            if (username && password) {
                alert(`مرحباً ${username}! تم استلام بيانات تسجيل الدخول بنجاح.`);
                // هنا يمكنك إضافة كود الإرسال إلى الخادم
            } else {
                alert('يرجى ملء جميع الحقول المطلوبة.');
            }
        });
        
        // إضافة تأثير بسيط عند التركيز على الحقول
        const inputs = document.querySelectorAll('input');
        inputs.forEach(input => {
            input.addEventListener('focus', function() {
                this.parentElement.style.transform = 'scale(1.01)';
            });
            
            input.addEventListener('blur', function() {
                this.parentElement.style.transform = 'scale(1)';
            });
        });
    </script>
</body>
</html>
