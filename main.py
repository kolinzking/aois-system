cat > main.py << 'EOF'                                                                            
  from fastapi import FastAPI             
                                                                                                    
  app = FastAPI()                                                                                   
   
  @app.get("/health")                                                                               
  def health():                                             
      return {"status": "ok"}                                                                       
  EOF    
